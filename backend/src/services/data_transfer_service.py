"""
CSV Contact Importer & Formula-Injection-Safe Export Service.

Design invariants:
- Formula Injection (CSV/Excel DDE) neutralization on all exported text cells.
- Zero silent truncation: invalid rows are quarantined with 1-based line numbers.
- Dry-Run validation preview prior to committing any database writes.
- Automatic header mapping for HubSpot, Salesforce, Pipedrive, and Spanish CSV exports.
"""

import csv
import io
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.entities import (
    Account,
    CompanyAffiliation,
    Contact,
    Deal,
    DealParticipant,
    DealStageHistory,
    ImportBatch,
    PipelineStage,
)
from src.schemas.crm import (
    CSVImportRequest,
    CSVImportResponse,
    CSVImportRowError,
    ImportBatchRollbackResponse,
)
from src.services.audit_service import record_entity_audit
from src.services.currency_service import (
    compute_normalized_usd_amount,
    resolve_exchange_rate_to_usd,
)
from src.services.pipeline_service import compute_forecast_category, ensure_default_pipeline

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")

_HEADER_ALIASES: dict[str, set[str]] = {
    "first_name": {"first_name", "first name", "firstname", "nombre", "nombres", "given name"},
    "last_name": {"last_name", "last name", "lastname", "apellido", "apellidos", "surname"},
    "email": {"email", "email address", "correo", "correo electronico", "e-mail", "work email"},
    "phone": {"phone", "phone number", "telefono", "teléfono", "mobile", "celular"},
    "job_title": {"job_title", "job title", "title", "cargo", "puesto", "role"},
    "company": {"company", "company name", "account", "account name", "empresa", "organizacion"},
    "lifecycle_stage": {"lifecycle_stage", "lifecycle stage", "stage", "etapa", "status"},
    "source_channel": {"source_channel", "lead source", "source", "origen", "canal", "utm_source"},
    "deal_title": {"deal_title", "deal name", "deal", "opportunity", "oportunidad", "trato"},
    "deal_amount": {"deal_amount", "deal amount", "amount", "monto", "valor"},
    "deal_currency": {"deal_currency", "currency", "divisa", "moneda"},
}

_VALID_LIFECYCLE_STAGES = {
    "lead",
    "marketing_qualified",
    "sales_qualified",
    "customer",
    "churned",
}


def sanitize_cell_for_export(value: Any) -> str:
    """Neutralize Excel/CSV DDE formula injection triggers by prefixing with a single quote."""
    if value is None:
        return ""
    text = str(value)
    if text.startswith(_FORMULA_TRIGGERS):
        return f"'{text}"
    return text


def _detect_column_mapping(
    raw_headers: list[str],
    explicit_map: dict[str, str] | None = None,
) -> dict[str, str]:
    """Map canonical CRM field names to the actual CSV header names."""
    mapping: dict[str, str] = {}
    normalized_lookup = {h.strip().lower(): h for h in raw_headers if h and h.strip()}

    for canonical, aliases in _HEADER_ALIASES.items():
        if explicit_map and canonical in explicit_map and explicit_map[canonical] in raw_headers:
            mapping[canonical] = explicit_map[canonical]
            continue
        for alias in aliases:
            if alias in normalized_lookup:
                mapping[canonical] = normalized_lookup[alias]
                break

    return mapping


async def import_contacts_csv(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    payload: CSVImportRequest,
) -> CSVImportResponse:
    """Validate and optionally commit a CSV batch of contacts with DLQ quarantine & deduplication."""
    reader = csv.DictReader(io.StringIO(payload.csv_content.strip()))
    raw_headers = list(reader.fieldnames or [])
    detected = _detect_column_mapping(raw_headers, payload.column_map)

    if "email" not in detected:
        return CSVImportResponse(
            dry_run=payload.dry_run,
            total_rows=0,
            would_create=0,
            would_update=0,
            would_skip=0,
            created_count=0,
            updated_count=0,
            skipped_count=0,
            quarantined_count=1,
            accounts_auto_created=0,
            detected_columns=detected,
            errors=[
                CSVImportRowError(
                    row=1,
                    email=None,
                    reason="CSV header must contain an email column (e.g. 'email', 'Email Address', 'correo').",
                )
            ],
        )

    existing_contacts = list(
        (
            await db.scalars(
                select(Contact).where(
                    Contact.tenant_id == tenant_id,
                    Contact.deleted_at.is_(None),
                )
            )
        ).all()
    )
    contacts_by_email: dict[str, Contact] = {c.email.lower(): c for c in existing_contacts}

    existing_accounts = list(
        (
            await db.scalars(
                select(Account).where(
                    Account.tenant_id == tenant_id,
                    Account.deleted_at.is_(None),
                )
            )
        ).all()
    )
    accounts_by_name: dict[str, Account] = {a.name.strip().lower(): a for a in existing_accounts}

    total_rows = 0
    would_create = 0
    would_update = 0
    would_skip = 0
    would_create_deals = 0
    created_count = 0
    updated_count = 0
    skipped_count = 0
    deals_created_count = 0
    accounts_auto_created = 0
    created_account_ids: list[str] = []
    created_contact_ids: list[str] = []
    created_deal_ids: list[str] = []
    errors: list[CSVImportRowError] = []
    seen_in_batch: set[str] = set()
    first_stage: PipelineStage | None = None

    async def _get_first_stage() -> PipelineStage:
        nonlocal first_stage
        if first_stage is None:
            stages = list(
                (
                    await db.scalars(
                        select(PipelineStage)
                        .where(PipelineStage.tenant_id == tenant_id)
                        .order_by(PipelineStage.position.asc())
                    )
                ).all()
            )
            if not stages:
                stages = await ensure_default_pipeline(db, tenant_id)
            first_stage = stages[0]
        return first_stage

    def _cell(row_dict: dict[str, str | None], field: str) -> str:
        col = detected.get(field)
        if not col:
            return ""
        return (row_dict.get(col) or "").strip()

    for line_num, row in enumerate(reader, start=2):
        if not any((v or "").strip() for v in row.values()):
            continue
        total_rows += 1

        raw_email = _cell(row, "email").lower()
        first_name = _cell(row, "first_name")
        last_name = _cell(row, "last_name")
        phone = _cell(row, "phone") or None
        job_title = _cell(row, "job_title") or None
        company_name = _cell(row, "company")
        source_channel = _cell(row, "source_channel").lower() or None
        raw_stage = _cell(row, "lifecycle_stage").lower()
        lifecycle_stage = raw_stage if raw_stage in _VALID_LIFECYCLE_STAGES else "lead"
        deal_title = _cell(row, "deal_title")
        raw_deal_amount = _cell(row, "deal_amount").replace(",", "").replace("$", "").strip()
        raw_deal_currency = (_cell(row, "deal_currency") or "USD").upper()[:3]
        deal_currency = raw_deal_currency if len(raw_deal_currency) == 3 and raw_deal_currency.isalpha() else "USD"
        parsed_deal_amount: Decimal | None = None
        if deal_title or raw_deal_amount:
            try:
                parsed_deal_amount = Decimal(raw_deal_amount) if raw_deal_amount else Decimal("0.00")
                if parsed_deal_amount < Decimal("0.00"):
                    raise ValueError("Negative amount")
            except (InvalidOperation, ValueError):
                errors.append(
                    CSVImportRowError(
                        row=line_num,
                        email=raw_email or None,
                        reason=f"Invalid deal amount: '{raw_deal_amount}'",
                    )
                )
                continue

        if not raw_email or not _EMAIL_RE.match(raw_email):
            errors.append(
                CSVImportRowError(
                    row=line_num,
                    email=raw_email or None,
                    reason=f"Invalid or missing email address: '{raw_email}'",
                )
            )
            continue

        if not first_name:
            # Infer fallback first name from email local part only when last_name is present, else quarantine
            if last_name:
                first_name = raw_email.split("@")[0].capitalize()
            else:
                errors.append(
                    CSVImportRowError(
                        row=line_num,
                        email=raw_email,
                        reason="Missing required 'first_name' column value.",
                    )
                )
                continue

        if not last_name:
            last_name = "-"

        if raw_email in seen_in_batch:
            would_skip += 1
            if not payload.dry_run:
                skipped_count += 1
            continue
        seen_in_batch.add(raw_email)

        existing = contacts_by_email.get(raw_email)
        if existing is not None:
            if payload.dedupe_strategy == "skip":
                would_skip += 1
                if not payload.dry_run:
                    skipped_count += 1
                continue

            would_update += 1
            if not payload.dry_run:
                existing.first_name = first_name[:100]
                existing.last_name = last_name[:100]
                if phone:
                    existing.phone = phone[:50]
                if job_title:
                    existing.job_title = job_title[:150]
                if source_channel:
                    existing.source_channel = source_channel[:100]
                if raw_stage in _VALID_LIFECYCLE_STAGES:
                    existing.lifecycle_stage = raw_stage
                updated_count += 1
            continue

        would_create += 1
        if deal_title:
            would_create_deals += 1
        if not payload.dry_run:
            resolved_account_id: uuid.UUID | None = None
            if company_name:
                acc_key = company_name.lower()
                acc = accounts_by_name.get(acc_key)
                if acc is None:
                    acc = Account(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        name=company_name[:255],
                        owner_id=actor_user_id,
                        metadata_={"created_via": "csv_import"},
                    )
                    db.add(acc)
                    await db.flush()
                    accounts_by_name[acc_key] = acc
                    accounts_auto_created += 1
                    created_account_ids.append(str(acc.id))
                resolved_account_id = acc.id

            new_contact = Contact(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                account_id=resolved_account_id,
                owner_id=actor_user_id,
                first_name=first_name[:100],
                last_name=last_name[:100],
                email=raw_email[:255],
                phone=phone[:50] if phone else None,
                job_title=job_title[:150] if job_title else None,
                lifecycle_stage=lifecycle_stage,
                source_channel=source_channel[:100] if source_channel else None,
                metadata_={"imported_via": "csv_import"},
            )
            db.add(new_contact)
            await db.flush()
            contacts_by_email[raw_email] = new_contact
            created_contact_ids.append(str(new_contact.id))

            if resolved_account_id is not None:
                db.add(
                    CompanyAffiliation(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        account_id=resolved_account_id,
                        contact_id=new_contact.id,
                        role_title=job_title[:150] if job_title else None,
                        is_primary=True,
                        is_active=True,
                    )
                )

            if deal_title:
                stage0 = await _get_first_stage()
                deal_amt = parsed_deal_amount if parsed_deal_amount is not None else Decimal("0.00")
                fx_rate = resolve_exchange_rate_to_usd(deal_currency, None)
                norm_usd = compute_normalized_usd_amount(deal_amt, fx_rate)
                now = datetime.now(UTC)
                new_deal = Deal(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    pipeline_id=stage0.pipeline_id,
                    stage_id=stage0.id,
                    account_id=resolved_account_id,
                    contact_id=new_contact.id,
                    owner_id=actor_user_id,
                    title=deal_title[:255],
                    amount=deal_amt,
                    currency=deal_currency,
                    exchange_rate_to_usd=fx_rate,
                    normalized_amount_usd=norm_usd,
                    forecast_category=compute_forecast_category(
                        win_probability=stage0.default_probability,
                        is_closed_won=stage0.is_closed_won,
                        is_closed_lost=stage0.is_closed_lost,
                    ),
                    win_probability=stage0.default_probability,
                    is_won=stage0.is_closed_won,
                    is_lost=stage0.is_closed_lost,
                    source_channel=source_channel[:100] if source_channel else None,
                    metadata_={"imported_via": "csv_import"},
                    stage_entered_at=now,
                )
                db.add(new_deal)
                await db.flush()
                db.add(
                    DealStageHistory(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        deal_id=new_deal.id,
                        from_stage_id=None,
                        to_stage_id=stage0.id,
                        amount_at_transition=new_deal.amount,
                        win_probability_at_transition=new_deal.win_probability,
                        changed_by=actor_user_id,
                        entered_at=now,
                    )
                )
                db.add(
                    DealParticipant(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        deal_id=new_deal.id,
                        contact_id=new_contact.id,
                        buying_role="champion",
                        is_primary=True,
                    )
                )
                created_deal_ids.append(str(new_deal.id))
                deals_created_count += 1

            created_count += 1

    import_batch_id: uuid.UUID | None = None
    if not payload.dry_run and (created_count > 0 or updated_count > 0 or deals_created_count > 0):
        batch = ImportBatch(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            created_by=actor_user_id,
            entity_scope="contacts_bundle",
            created_account_ids=created_account_ids,
            created_contact_ids=created_contact_ids,
            created_deal_ids=created_deal_ids,
            status="committed",
        )
        db.add(batch)
        import_batch_id = batch.id
        await record_entity_audit(
            db,
            tenant_id=tenant_id,
            entity_type="contact",
            entity_id=batch.id,
            action="CSV_IMPORT",
            actor_user_id=actor_user_id,
            changes={
                "batch_id": str(batch.id),
                "created_count": created_count,
                "updated_count": updated_count,
                "skipped_count": skipped_count,
                "deals_created_count": deals_created_count,
                "quarantined_count": len(errors),
                "accounts_auto_created": accounts_auto_created,
            },
        )
        await db.flush()

    return CSVImportResponse(
        dry_run=payload.dry_run,
        import_batch_id=import_batch_id,
        total_rows=total_rows,
        would_create=would_create,
        would_update=would_update,
        would_skip=would_skip,
        would_create_deals=would_create_deals,
        created_count=created_count,
        updated_count=updated_count,
        skipped_count=skipped_count,
        deals_created_count=deals_created_count,
        quarantined_count=len(errors),
        accounts_auto_created=accounts_auto_created,
        detected_columns=detected,
        errors=errors,
    )


async def rollback_import_batch(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    batch_id: uuid.UUID,
) -> ImportBatchRollbackResponse:
    """Atomically soft-deletes all accounts, contacts, and deals created by a CSV import batch."""
    batch = await db.scalar(
        select(ImportBatch).where(
            ImportBatch.id == batch_id,
            ImportBatch.tenant_id == tenant_id,
        )
    )
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import batch {batch_id} not found.",
        )
    if batch.status == "rolled_back":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This import batch has already been rolled back.",
        )

    now = datetime.now(UTC)
    deal_uuids = [uuid.UUID(x) for x in (batch.created_deal_ids or [])]
    contact_uuids = [uuid.UUID(x) for x in (batch.created_contact_ids or [])]
    account_uuids = [uuid.UUID(x) for x in (batch.created_account_ids or [])]

    reverted_deals = 0
    reverted_contacts = 0
    reverted_accounts = 0

    if deal_uuids:
        await db.execute(
            update(Deal)
            .where(Deal.tenant_id == tenant_id, Deal.id.in_(deal_uuids), Deal.deleted_at.is_(None))
            .values(deleted_at=now)
        )
        reverted_deals = len(deal_uuids)

    if contact_uuids:
        await db.execute(
            update(Contact)
            .where(
                Contact.tenant_id == tenant_id,
                Contact.id.in_(contact_uuids),
                Contact.deleted_at.is_(None),
            )
            .values(deleted_at=now)
        )
        reverted_contacts = len(contact_uuids)

    if account_uuids:
        await db.execute(
            update(Account)
            .where(
                Account.tenant_id == tenant_id,
                Account.id.in_(account_uuids),
                Account.deleted_at.is_(None),
            )
            .values(deleted_at=now)
        )
        reverted_accounts = len(account_uuids)

    batch.status = "rolled_back"
    batch.rolled_back_at = now

    await record_entity_audit(
        db,
        tenant_id=tenant_id,
        entity_type="import_batch",
        entity_id=batch.id,
        action="CSV_IMPORT_ROLLBACK",
        actor_user_id=actor_user_id,
        changes={
            "reverted_accounts": reverted_accounts,
            "reverted_contacts": reverted_contacts,
            "reverted_deals": reverted_deals,
        },
    )
    await db.flush()

    return ImportBatchRollbackResponse(
        batch_id=batch.id,
        status=batch.status,
        reverted_accounts=reverted_accounts,
        reverted_contacts=reverted_contacts,
        reverted_deals=reverted_deals,
    )


async def export_entity_csv(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    entity: str,
) -> str:
    """Export tenant-scoped CRM entities to CSV with strict Formula Injection neutralization."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")

    if entity == "contacts":
        writer.writerow(
            [
                "id",
                "first_name",
                "last_name",
                "email",
                "phone",
                "job_title",
                "lifecycle_stage",
                "source_channel",
                "lead_score",
                "created_at",
            ]
        )
        rows = list(
            (
                await db.scalars(
                    select(Contact)
                    .where(Contact.tenant_id == tenant_id, Contact.deleted_at.is_(None))
                    .order_by(Contact.created_at.desc())
                )
            ).all()
        )
        for c in rows:
            writer.writerow(
                [
                    sanitize_cell_for_export(c.id),
                    sanitize_cell_for_export(c.first_name),
                    sanitize_cell_for_export(c.last_name),
                    sanitize_cell_for_export(c.email),
                    sanitize_cell_for_export(c.phone),
                    sanitize_cell_for_export(c.job_title),
                    sanitize_cell_for_export(c.lifecycle_stage),
                    sanitize_cell_for_export(c.source_channel),
                    f"{c.lead_score:.2f}",
                    c.created_at.isoformat(),
                ]
            )
    elif entity == "deals":
        writer.writerow(
            [
                "id",
                "title",
                "amount",
                "currency",
                "exchange_rate_to_usd",
                "normalized_amount_usd",
                "forecast_category",
                "win_probability",
                "is_won",
                "is_lost",
                "source_channel",
                "expected_close_date",
                "close_date_push_count",
            ]
        )
        deal_rows = list(
            (
                await db.scalars(
                    select(Deal)
                    .where(Deal.tenant_id == tenant_id, Deal.deleted_at.is_(None))
                    .order_by(Deal.created_at.desc())
                )
            ).all()
        )
        for d in deal_rows:
            writer.writerow(
                [
                    sanitize_cell_for_export(d.id),
                    sanitize_cell_for_export(d.title),
                    f"{d.amount:.2f}",
                    sanitize_cell_for_export(d.currency),
                    f"{d.exchange_rate_to_usd:.6f}",
                    f"{d.normalized_amount_usd:.2f}",
                    sanitize_cell_for_export(d.forecast_category),
                    f"{d.win_probability:.2f}",
                    str(d.is_won),
                    str(d.is_lost),
                    sanitize_cell_for_export(d.source_channel),
                    d.expected_close_date.isoformat() if d.expected_close_date else "",
                    str(d.close_date_push_count or 0),
                ]
            )
    else:
        writer.writerow(
            [
                "id",
                "name",
                "industry",
                "website",
                "annual_revenue",
                "employee_count",
                "created_at",
            ]
        )
        acc_rows = list(
            (
                await db.scalars(
                    select(Account)
                    .where(Account.tenant_id == tenant_id, Account.deleted_at.is_(None))
                    .order_by(func.lower(Account.name).asc())
                )
            ).all()
        )
        for a in acc_rows:
            writer.writerow(
                [
                    sanitize_cell_for_export(a.id),
                    sanitize_cell_for_export(a.name),
                    sanitize_cell_for_export(a.industry),
                    sanitize_cell_for_export(a.website),
                    f"{a.annual_revenue:.2f}" if a.annual_revenue is not None else "",
                    str(a.employee_count) if a.employee_count is not None else "",
                    a.created_at.isoformat(),
                ]
            )

    return buf.getvalue()
