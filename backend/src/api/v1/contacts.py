"""
Contacts API Router: Tenant-Scoped CRUD, Deduplication, Semantic Indexing & Outbox Events.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_tenant_db, require_roles
from src.models.entities import Contact, OutboxEvent
from src.schemas.crm import AuthenticatedUser, ContactCreate, ContactResponse, ContactUpdate
from src.services.embedding_service import upsert_entity_embedding

router = APIRouter(prefix="/contacts", tags=["Contacts"])

_WRITE_ROLES = ["admin", "sales_manager", "sales_rep"]


@router.get(
    "",
    response_model=list[ContactResponse],
    status_code=status.HTTP_200_OK,
    summary="List contacts belonging to the current tenant",
)
async def list_contacts(
    q: str | None = Query(default=None, max_length=120),
    lifecycle_stage: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    stmt = select(Contact).where(Contact.tenant_id == current_user.tenant_id)
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

    stmt = stmt.order_by(Contact.created_at.desc()).offset(offset).limit(limit)
    contacts = await db.scalars(stmt)
    return list(contacts.all())


@router.post(
    "",
    response_model=ContactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new contact with deduplication, semantic indexing, and atomic outbox event",
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
        )
    )
    if existing_contact:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A contact with email '{normalized_email}' already exists in this tenant (ID: {existing_contact.id}).",
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
        metadata_=payload.metadata,
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
    summary="Fetch a single contact by ID",
)
async def get_contact(
    contact_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    contact = await db.scalar(
        select(Contact).where(Contact.id == contact_id, Contact.tenant_id == current_user.tenant_id)
    )
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Contact {contact_id} not found.")
    return contact


@router.patch(
    "/{contact_id}",
    response_model=ContactResponse,
    status_code=status.HTTP_200_OK,
    summary="Update an existing contact",
)
async def update_contact(
    contact_id: uuid.UUID,
    payload: ContactUpdate,
    current_user: AuthenticatedUser = Depends(require_roles(_WRITE_ROLES)),
    db: AsyncSession = Depends(get_tenant_db),
):
    contact = await db.scalar(
        select(Contact).where(Contact.id == contact_id, Contact.tenant_id == current_user.tenant_id)
    )
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Contact {contact_id} not found.")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(contact, field, value)

    await db.flush()
    await db.refresh(contact)
    return contact


@router.delete(
    "/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a contact belonging to the current tenant",
)
async def delete_contact(
    contact_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(require_roles(["admin", "sales_manager"])),
    db: AsyncSession = Depends(get_tenant_db),
):
    contact = await db.scalar(
        select(Contact).where(Contact.id == contact_id, Contact.tenant_id == current_user.tenant_id)
    )
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Contact {contact_id} not found.")

    await db.delete(contact)
    await db.flush()
    return None
