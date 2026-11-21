"""
Email & Calendar Synchronization Ingestion Engine.
Implements:
1. Idempotent deduplication by RFC 5322 `Message-ID` across multiple CC'd sales reps.
2. Thread resolution (`thread_id` / `in_reply_to`) and automatic Deal / Account roll-up linking.
3. Automated noise filtering (Out-of-Office `Auto-Submitted`, bulk newsletters `Precedence: bulk`).
4. Privacy auto-exclusion for internal workspace domains and sensitive prefixes (`hr@`, `payroll@`, `legal@`).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.entities import Account, Contact, Deal, Interaction, SyncedEmailMessage
from src.schemas.crm import AuthenticatedUser, EmailSyncIngestRequest, EmailSyncIngestResponse
from src.services.audit_service import resolve_interaction_hierarchy
from src.services.rbac_service import get_tenant_settings

_SENSITIVE_LOCAL_PREFIXES = {
    "hr",
    "payroll",
    "nomina",
    "legal",
    "compliance",
    "security-incident",
    "board",
}


def _extract_domain(email_addr: str) -> str:
    parts = email_addr.strip().lower().split("@")
    return parts[1] if len(parts) == 2 else ""


def _extract_local_part(email_addr: str) -> str:
    return email_addr.strip().lower().split("@")[0]


def _is_automated_noise(headers: dict[str, str], subject: str) -> str | None:
    normalized = {k.strip().lower(): v.strip().lower() for k, v in headers.items()}

    auto_submitted = normalized.get("auto-submitted", "no")
    if auto_submitted != "no":
        return f"Filtered automated message (Auto-Submitted: {auto_submitted})"

    if "x-autoreply" in normalized or "x-autorespond" in normalized:
        return "Filtered auto-reply header"

    precedence = normalized.get("precedence", "")
    if precedence in {"bulk", "list", "junk"}:
        return f"Filtered bulk mailing list message (Precedence: {precedence})"

    if "list-unsubscribe" in normalized and not subject.strip().lower().startswith("re:"):
        return "Filtered newsletter with List-Unsubscribe header"

    return None


def _is_internal_or_sensitive(
    sender_email: str,
    recipient_emails: list[str],
    internal_domains: set[str],
) -> str | None:
    all_participants = [sender_email.strip().lower(), *[r.strip().lower() for r in recipient_emails]]

    # 1. Block sensitive internal mailboxes (HR, Payroll, Legal)
    for addr in all_participants:
        local = _extract_local_part(addr)
        domain = _extract_domain(addr)
        if local in _SENSITIVE_LOCAL_PREFIXES and (not internal_domains or domain in internal_domains):
            return f"Excluded sensitive mailbox address '{addr}'"

    # 2. Block purely internal team conversations where 100% of participants share internal domains
    if internal_domains:
        all_internal = all(_extract_domain(addr) in internal_domains for addr in all_participants)
        if all_internal:
            return "Excluded internal-only conversation across workspace domain"

    return None


async def ingest_synced_email(
    session: AsyncSession,
    current_user: AuthenticatedUser,
    payload: EmailSyncIngestRequest,
) -> tuple[EmailSyncIngestResponse, bool]:
    """
    Processes an incoming synced email event.
    Returns `(response, is_newly_created)`.
    """
    tenant_id = current_user.tenant_id
    rfc_id = payload.rfc_message_id.strip()
    mailbox = str(payload.mailbox_email).strip().lower()
    sender = str(payload.sender_email).strip().lower()
    recipients = [str(r).strip().lower() for r in payload.recipient_emails]

    # 1. Check automated noise headers first
    noise_reason = _is_automated_noise(payload.headers, payload.subject)
    if noise_reason:
        return (
            EmailSyncIngestResponse(
                status="filtered_noise",
                rfc_message_id=rfc_id,
                reason=noise_reason,
            ),
            False,
        )

    # 2. Check internal domain & sensitive mailbox privacy boundaries
    tenant_cfg = await get_tenant_settings(session, tenant_id)
    configured_domains = {d.strip().lower() for d in tenant_cfg.get("internal_domains", []) if d}
    if not configured_domains:
        # Infer default internal domain from the syncing mailbox if not explicitly configured
        mailbox_domain = _extract_domain(mailbox)
        if mailbox_domain:
            configured_domains = {mailbox_domain}

    exclusion_reason = _is_internal_or_sensitive(sender, recipients, configured_domains)
    if exclusion_reason:
        return (
            EmailSyncIngestResponse(
                status="excluded_internal_or_sensitive",
                rfc_message_id=rfc_id,
                reason=exclusion_reason,
            ),
            False,
        )

    # 3. Check RFC 5322 Message-ID idempotency within the tenant
    existing_sync = await session.scalar(
        select(SyncedEmailMessage).where(
            SyncedEmailMessage.tenant_id == tenant_id,
            SyncedEmailMessage.rfc_message_id == rfc_id,
        )
    )
    if existing_sync:
        mailboxes = list(existing_sync.synced_mailboxes or [])
        if mailbox not in mailboxes:
            mailboxes.append(mailbox)
            existing_sync.synced_mailboxes = mailboxes
            await session.flush()

        return (
            EmailSyncIngestResponse(
                status="deduplicated",
                rfc_message_id=rfc_id,
                interaction_id=existing_sync.interaction_id,
                contact_id=existing_sync.contact_id,
                account_id=existing_sync.account_id,
                deal_id=existing_sync.deal_id,
                synced_mailboxes=mailboxes,
                reason="Duplicate RFC 5322 Message-ID merged into existing timeline interaction.",
            ),
            False,
        )

    # 4. Resolve external participant(s) to Contact, Account, and active Deal
    external_emails = [
        addr for addr in [sender, *recipients] if _extract_domain(addr) not in configured_domains
    ]
    matched_contact: Contact | None = None
    if external_emails:
        matched_contact = await session.scalar(
            select(Contact).where(
                Contact.tenant_id == tenant_id,
                Contact.deleted_at.is_(None),
                Contact.email.in_(external_emails),
            )
        )

    # Also check thread continuity if reply in an existing thread
    parent_deal_id: uuid.UUID | None = None
    parent_account_id: uuid.UUID | None = None
    if payload.thread_id:
        thread_match = await session.scalar(
            select(SyncedEmailMessage).where(
                SyncedEmailMessage.tenant_id == tenant_id,
                SyncedEmailMessage.thread_id == payload.thread_id,
            )
        )
        if thread_match:
            parent_deal_id = thread_match.deal_id
            parent_account_id = thread_match.account_id
            if matched_contact is None and thread_match.contact_id:
                matched_contact = await session.scalar(
                    select(Contact).where(
                        Contact.id == thread_match.contact_id,
                        Contact.tenant_id == tenant_id,
                    )
                )

    contact_id = matched_contact.id if matched_contact else None
    account_id = matched_contact.account_id if matched_contact and matched_contact.account_id else parent_account_id

    # If account_id is still None, attempt domain resolution against Account.website
    if account_id is None and external_emails:
        ext_domain = _extract_domain(external_emails[0])
        if ext_domain:
            matched_acc = await session.scalar(
                select(Account.id).where(
                    Account.tenant_id == tenant_id,
                    Account.deleted_at.is_(None),
                    Account.website.ilike(f"%{ext_domain}%"),
                )
            )
            if matched_acc:
                account_id = matched_acc

    # Find most recent open Deal for this contact or account if not resolved from thread
    deal_id = parent_deal_id
    if deal_id is None and contact_id is not None:
        deal_id = await session.scalar(
            select(Deal.id)
            .where(
                Deal.tenant_id == tenant_id,
                Deal.contact_id == contact_id,
                Deal.deleted_at.is_(None),
                Deal.is_won.is_(False),
                Deal.is_lost.is_(False),
            )
            .order_by(Deal.created_at.desc())
            .limit(1)
        )

    occurred = payload.occurred_at or datetime.now(UTC)
    direction = "outbound" if _extract_domain(sender) in configured_domains else "inbound"

    account_id, deal_id, contact_id = await resolve_interaction_hierarchy(
        session,
        tenant_id=tenant_id,
        account_id=account_id,
        deal_id=deal_id,
        contact_id=contact_id,
        occurred_at=occurred,
    )

    interaction = Interaction(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=current_user.id,
        contact_id=contact_id,
        account_id=account_id,
        deal_id=deal_id,
        type="email",
        direction=direction,
        subject=payload.subject.strip(),
        content_body=payload.body_text.strip(),
        occurred_at=occurred,
        metadata_={
            "rfc_message_id": rfc_id,
            "thread_id": payload.thread_id,
            "sender_email": sender,
            "recipient_emails": recipients,
        },
    )
    session.add(interaction)
    await session.flush()

    synced_msg = SyncedEmailMessage(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        rfc_message_id=rfc_id,
        thread_id=payload.thread_id,
        in_reply_to=payload.in_reply_to,
        sender_email=sender,
        recipient_emails=recipients,
        synced_mailboxes=[mailbox],
        interaction_id=interaction.id,
        contact_id=contact_id,
        account_id=account_id,
        deal_id=deal_id,
    )
    session.add(synced_msg)
    await session.flush()

    return (
        EmailSyncIngestResponse(
            status="ingested",
            rfc_message_id=rfc_id,
            interaction_id=interaction.id,
            contact_id=contact_id,
            account_id=account_id,
            deal_id=deal_id,
            synced_mailboxes=[mailbox],
        ),
        True,
    )
