"""
Contacts API Router: Tenant-Scoped CRUD, Custom Fields Validation, Multi-Company Affiliations,
Non-Destructive Contact Merge, Soft Delete, Roll-Up Timeline, Semantic Indexing & Outbox Events.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_tenant_db, require_roles
from src.models.entities import (
    Account,
    CompanyAffiliation,
    Contact,
    Deal,
    DealParticipant,
    Interaction,
    OutboxEvent,
    Task,
)
from src.schemas.crm import (
    AuthenticatedUser,
    CompanyAffiliationResponse,
    ContactCreate,
    ContactMergeRequest,
    ContactResponse,
    ContactUpdate,
    CursorPaginatedTimelineResponse,
    InteractionResponse,
)
from src.services.audit_service import (
    apply_sql_keyset_cursor,
    paginate_interactions_with_cursor,
    record_entity_audit,
    slice_keyset_page,
)
from src.services.custom_fields_service import (
    matches_custom_field_filter,
    validate_entity_custom_fields,
)
from src.services.embedding_service import upsert_entity_embedding
from src.services.rbac_service import get_visible_owner_ids, verify_record_access

router = APIRouter(prefix="/contacts", tags=["Contacts"])

_WRITE_ROLES = ["admin", "sales_manager", "sales_rep"]


@router.get(
    "",
    response_model=list[ContactResponse],
    status_code=status.HTTP_200_OK,
    summary="List contacts belonging to the current tenant with RBAC and custom field filtering",
)
async def list_contacts(
    response: Response,
    q: str | None = Query(default=None, max_length=120),
    lifecycle_stage: str | None = Query(default=None),
    cf_key: str | None = Query(default=None, max_length=100),
    cf_value: str | None = Query(default=None, max_length=255),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    stmt = select(Contact).where(
        Contact.tenant_id == current_user.tenant_id,
        Contact.deleted_at.is_(None),
    )

    visible_owners = await get_visible_owner_ids(db, current_user)
    if visible_owners is not None:
        stmt = stmt.where(Contact.owner_id.in_(visible_owners))

    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Contact.first_name.ilike(pattern),
                Contact.last_name.ilike(pattern),
                Contact.email.ilike(pattern),
                Contact.job_title.ilike(pattern),
            )
        )
    if lifecycle_stage:
        stmt = stmt.where(Contact.lifecycle_stage == lifecycle_stage)

    stmt = apply_sql_keyset_cursor(stmt, Contact, cursor)
    stmt = stmt.order_by(Contact.created_at.desc(), Contact.id.desc())
    if not cf_key:
        stmt = stmt.limit(limit + 1)

    rows = list((await db.scalars(stmt)).all())
    if cf_key:
        rows = [c for c in rows if matches_custom_field_filter(c.metadata_, cf_key, cf_value)]

    page, next_cursor = slice_keyset_page(rows, limit)
    if next_cursor:
        response.headers["X-Next-Cursor"] = next_cursor
    return page


@router.post(
    "",
    response_model=ContactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new contact with custom field validation, deduplication, semantic indexing, and outbox event",
)
async def create_contact(
    payload: ContactCreate,
    current_user: AuthenticatedUser = Depends(require_roles(_WRITE_ROLES)),
    db: AsyncSession = Depends(get_tenant_db),
):
    normalized_email = str(payload.email).strip().lower()
    existing_contact = await db.scalar(
        select(Contact).where(
            Contact.tenant_id == current_user.tenant_id,
            Contact.email == normalized_email,
            Contact.deleted_at.is_(None),
        )
    )
    if existing_contact:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A contact with email '{normalized_email}' already exists in this tenant (ID: {existing_contact.id}).",
        )

    if payload.account_id:
        acc_exists = await db.scalar(
            select(Account.id).where(
                Account.id == payload.account_id,
                Account.tenant_id == current_user.tenant_id,
                Account.deleted_at.is_(None),
            )
        )
        if not acc_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account {payload.account_id} not found in this tenant.",
            )

    validated_metadata = await validate_entity_custom_fields(
        db,
        current_user.tenant_id,
        "contact",
        payload.metadata,
    )

    new_contact = Contact(
        id=uuid.uuid4(),
        tenant_id=current_user.tenant_id,
        account_id=payload.account_id,
        owner_id=current_user.id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=normalized_email,
        phone=payload.phone,
        job_title=payload.job_title,
        lifecycle_stage=payload.lifecycle_stage,
        source_channel=payload.source_channel.lower() if payload.source_channel else None,
        metadata_=validated_metadata,
    )
    db.add(new_contact)

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A contact with email '{normalized_email}' already exists in this tenant.",
        ) from exc

    if payload.account_id:
        db.add(
            CompanyAffiliation(
                id=uuid.uuid4(),
                tenant_id=current_user.tenant_id,
                account_id=payload.account_id,
                contact_id=new_contact.id,
                role_title=payload.job_title,
                is_primary=True,
                is_active=True,
            )
        )

    profile_summary = (
        f"{new_contact.first_name} {new_contact.last_name} ({new_contact.email}) "
        f"- {new_contact.job_title or 'N/A'} [{new_contact.lifecycle_stage}]"
    )
    await upsert_entity_embedding(
        session=db,
        tenant_id=current_user.tenant_id,
        entity_type="contact",
        entity_id=new_contact.id,
        text_content=profile_summary,
    )

    await record_entity_audit(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="contact",
        entity_id=new_contact.id,
        action="CREATE",
        actor_user_id=current_user.id,
        changes={"email": new_contact.email, "account_id": str(payload.account_id) if payload.account_id else None},
    )

    outbox_event = OutboxEvent(
        id=uuid.uuid4(),
        tenant_id=current_user.tenant_id,
        aggregate_type="contact",
        aggregate_id=new_contact.id,
        event_type="ContactCreated",
        payload={
            "contact_id": str(new_contact.id),
            "email": new_contact.email,
            "full_name": f"{new_contact.first_name} {new_contact.last_name}",
            "created_by": str(current_user.id),
            "tenant_id": str(current_user.tenant_id),
        },
        status="pending",
    )
    db.add(outbox_event)
    await db.flush()
    await db.refresh(new_contact)
    return new_contact


@router.get(
    "/{contact_id}",
    response_model=ContactResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch a single contact by ID (transparently follows merged_into_id pointers)",
)
async def get_contact(
    contact_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    contact = await db.scalar(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.tenant_id == current_user.tenant_id,
        )
    )
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Contact {contact_id} not found.")

    # Follow merged_into_id chain up to 5 hops so legacy bookmarks/webhooks never fail with 404
    hops = 0
    while contact and contact.merged_into_id is not None and hops < 5:
        contact = await db.scalar(
            select(Contact).where(
                Contact.id == contact.merged_into_id,
                Contact.tenant_id == current_user.tenant_id,
            )
        )
        hops += 1

    if not contact or contact.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Contact {contact_id} not found.")

    await verify_record_access(db, current_user, contact.owner_id, require_write=False)
    return contact


@router.patch(
    "/{contact_id}",
    response_model=ContactResponse,
    status_code=status.HTTP_200_OK,
    summary="Update an existing contact with custom field validation and RBAC ownership check",
)
async def update_contact(
    contact_id: uuid.UUID,
    payload: ContactUpdate,
    current_user: AuthenticatedUser = Depends(require_roles(_WRITE_ROLES)),
    db: AsyncSession = Depends(get_tenant_db),
):
    contact = await db.scalar(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.tenant_id == current_user.tenant_id,
            Contact.deleted_at.is_(None),
        )
    )
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Contact {contact_id} not found.")

    await verify_record_access(db, current_user, contact.owner_id, require_write=True)

    updates = payload.model_dump(exclude_unset=True)
    changes_diff: dict[str, dict[str, str | None]] = {}

    if "metadata" in updates:
        raw_meta = updates.pop("metadata")
        contact.metadata_ = await validate_entity_custom_fields(
            db,
            current_user.tenant_id,
            "contact",
            raw_meta,
            is_partial=True,
            existing_metadata=contact.metadata_,
        )
        changes_diff["metadata"] = {"new": str(raw_meta)}

    for field, value in updates.items():
        old_val = getattr(contact, field, None)
        setattr(contact, field, value)
        changes_diff[field] = {
            "old": str(old_val) if old_val is not None else None,
            "new": str(value) if value is not None else None,
        }

    await record_entity_audit(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="contact",
        entity_id=contact.id,
        action="UPDATE",
        actor_user_id=current_user.id,
        changes=changes_diff,
    )

    await db.flush()
    await db.refresh(contact)
    return contact


@router.delete(
    "/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a contact while preserving associated deal interactions and historical timeline",
)
async def delete_contact(
    contact_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(require_roles(["admin", "sales_manager"])),
    db: AsyncSession = Depends(get_tenant_db),
):
    contact = await db.scalar(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.tenant_id == current_user.tenant_id,
            Contact.deleted_at.is_(None),
        )
    )
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Contact {contact_id} not found.")

    now = datetime.now(UTC)
    original_email = contact.email
    contact.deleted_at = now
    contact.email = f"{original_email}#deleted-{contact.id.hex[:8]}"

    await record_entity_audit(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="contact",
        entity_id=contact.id,
        action="SOFT_DELETE",
        actor_user_id=current_user.id,
        changes={"deleted_email": original_email, "deleted_at": now.isoformat()},
    )
    await db.flush()
    return None


@router.post(
    "/{contact_id}/restore",
    response_model=ContactResponse,
    status_code=status.HTTP_200_OK,
    summary="Restore a soft-deleted contact (Undo Delete)",
)
async def restore_contact(
    contact_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(require_roles(["admin", "sales_manager"])),
    db: AsyncSession = Depends(get_tenant_db),
):
    contact = await db.scalar(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.tenant_id == current_user.tenant_id,
            Contact.deleted_at.is_not(None),
            Contact.merged_into_id.is_(None),
        )
    )
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Soft-deleted contact {contact_id} not found.",
        )

    restored_email = contact.email.split("#deleted-")[0]
    contact.email = restored_email
    contact.deleted_at = None

    await record_entity_audit(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="contact",
        entity_id=contact.id,
        action="RESTORE",
        actor_user_id=current_user.id,
        changes={"restored_email": restored_email},
    )
    await db.flush()
    await db.refresh(contact)
    return contact


@router.get(
    "/{contact_id}/affiliations",
    response_model=list[CompanyAffiliationResponse],
    status_code=status.HTTP_200_OK,
    summary="List all company affiliations for a contact",
)
async def list_contact_affiliations(
    contact_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    contact = await db.scalar(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.tenant_id == current_user.tenant_id,
            Contact.deleted_at.is_(None),
        )
    )
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Contact {contact_id} not found.")

    rows = await db.scalars(
        select(CompanyAffiliation)
        .where(
            CompanyAffiliation.tenant_id == current_user.tenant_id,
            CompanyAffiliation.contact_id == contact_id,
        )
        .order_by(CompanyAffiliation.is_primary.desc(), CompanyAffiliation.created_at.asc())
    )
    return list(rows.all())


@router.get(
    "/{contact_id}/timeline",
    response_model=CursorPaginatedTimelineResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch chronological activity timeline for a contact with keyset cursor pagination",
)
async def get_contact_timeline(
    contact_id: uuid.UUID,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    contact = await db.scalar(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.tenant_id == current_user.tenant_id,
            Contact.deleted_at.is_(None),
        )
    )
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Contact {contact_id} not found.")

    await verify_record_access(db, current_user, contact.owner_id, require_write=False)

    all_interactions = list(
        (
            await db.scalars(
                select(Interaction)
                .where(
                    Interaction.tenant_id == current_user.tenant_id,
                    Interaction.contact_id == contact_id,
                )
                .order_by(Interaction.occurred_at.desc(), Interaction.id.desc())
            )
        ).all()
    )

    page_items, next_cursor = paginate_interactions_with_cursor(all_interactions, cursor, limit)
    return CursorPaginatedTimelineResponse(
        items=[InteractionResponse.model_validate(item) for item in page_items],
        next_cursor=next_cursor,
    )


@router.post(
    "/{target_contact_id}/merge",
    response_model=ContactResponse,
    status_code=status.HTTP_200_OK,
    summary="Non-destructively merge a duplicate contact into target contact, re-linking deals, interactions & tasks",
)
async def merge_contacts(
    target_contact_id: uuid.UUID,
    payload: ContactMergeRequest,
    current_user: AuthenticatedUser = Depends(require_roles(["admin", "sales_manager"])),
    db: AsyncSession = Depends(get_tenant_db),
):
    if target_contact_id == payload.source_contact_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot merge a contact into itself.",
        )

    target = await db.scalar(
        select(Contact).where(
            Contact.id == target_contact_id,
            Contact.tenant_id == current_user.tenant_id,
            Contact.deleted_at.is_(None),
        )
    )
    source = await db.scalar(
        select(Contact).where(
            Contact.id == payload.source_contact_id,
            Contact.tenant_id == current_user.tenant_id,
            Contact.deleted_at.is_(None),
        )
    )
    if not target or not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target or source contact not found in this tenant.",
        )

    # 1. Re-link Deals, Interactions, and Tasks from source to target
    await db.execute(
        update(Deal)
        .where(Deal.tenant_id == current_user.tenant_id, Deal.contact_id == source.id)
        .values(contact_id=target.id)
    )
    await db.execute(
        update(Interaction)
        .where(Interaction.tenant_id == current_user.tenant_id, Interaction.contact_id == source.id)
        .values(contact_id=target.id)
    )
    await db.execute(
        update(Task)
        .where(Task.tenant_id == current_user.tenant_id, Task.contact_id == source.id)
        .values(contact_id=target.id)
    )

    # 2. Re-link non-conflicting CompanyAffiliations & DealParticipants
    target_aff_accounts = set(
        (
            await db.scalars(
                select(CompanyAffiliation.account_id).where(
                    CompanyAffiliation.tenant_id == current_user.tenant_id,
                    CompanyAffiliation.contact_id == target.id,
                )
            )
        ).all()
    )
    source_affs = list(
        (
            await db.scalars(
                select(CompanyAffiliation).where(
                    CompanyAffiliation.tenant_id == current_user.tenant_id,
                    CompanyAffiliation.contact_id == source.id,
                )
            )
        ).all()
    )
    for aff in source_affs:
        if aff.account_id not in target_aff_accounts:
            aff.contact_id = target.id
            aff.is_primary = False
        else:
            await db.delete(aff)

    target_part_deals = set(
        (
            await db.scalars(
                select(DealParticipant.deal_id).where(
                    DealParticipant.tenant_id == current_user.tenant_id,
                    DealParticipant.contact_id == target.id,
                )
            )
        ).all()
    )
    source_parts = list(
        (
            await db.scalars(
                select(DealParticipant).where(
                    DealParticipant.tenant_id == current_user.tenant_id,
                    DealParticipant.contact_id == source.id,
                )
            )
        ).all()
    )
    for part in source_parts:
        if part.deal_id not in target_part_deals:
            part.contact_id = target.id
        else:
            await db.delete(part)

    # 3. Enrich target profile fields & preserve secondary email in metadata
    if not target.phone and source.phone:
        target.phone = source.phone
    if not target.job_title and source.job_title:
        target.job_title = source.job_title
    if not target.account_id and source.account_id:
        target.account_id = source.account_id

    merged_meta = dict(source.metadata_ or {})
    merged_meta.update(target.metadata_ or {})
    secondary_emails = list(merged_meta.get("secondary_emails", []))
    source_original_email = source.email
    if source_original_email not in secondary_emails and source_original_email != target.email:
        secondary_emails.append(source_original_email)
    merged_meta["secondary_emails"] = secondary_emails
    target.metadata_ = merged_meta

    # 4. Soft-delete source contact and record merged_into_id redirect pointer
    now = datetime.now(UTC)
    source.merged_into_id = target.id
    source.deleted_at = now
    source.email = f"{source_original_email}#merged-{source.id.hex[:8]}"

    await record_entity_audit(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="contact",
        entity_id=target.id,
        action="MERGE",
        actor_user_id=current_user.id,
        changes={
            "source_contact_id": str(source.id),
            "source_email": source_original_email,
            "target_contact_id": str(target.id),
        },
    )

    db.add(
        OutboxEvent(
            id=uuid.uuid4(),
            tenant_id=current_user.tenant_id,
            aggregate_type="contact",
            aggregate_id=target.id,
            event_type="ContactMerged",
            payload={
                "target_contact_id": str(target.id),
                "source_contact_id": str(source.id),
                "merged_email": source_original_email,
                "merged_by": str(current_user.id),
            },
            status="pending",
        )
    )

    await db.flush()
    await db.refresh(target)
    return target
