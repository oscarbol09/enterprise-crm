"""
Custom Field Registry, Unified Interaction Logging & System Entity Audit Log Routers.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_tenant_db, require_roles
from src.models.entities import CustomFieldDefinition, EntityAuditLog, Interaction, OutboxEvent
from src.schemas.crm import (
    AuthenticatedUser,
    CustomFieldDefinitionCreate,
    CustomFieldDefinitionResponse,
    EntityAuditLogResponse,
    InteractionCreate,
    InteractionResponse,
)
from src.services.audit_service import record_entity_audit, resolve_interaction_hierarchy

custom_fields_router = APIRouter(prefix="/custom-fields", tags=["Custom Fields & Schema Registry"])
interactions_router = APIRouter(prefix="/interactions", tags=["Interactions & Activity Timeline"])
audit_logs_router = APIRouter(prefix="/audit-logs", tags=["System Audit Trail"])

_ADMIN_MANAGER_ROLES = ["admin", "sales_manager"]
_WRITE_ROLES = ["admin", "sales_manager", "sales_rep"]


@custom_fields_router.get(
    "",
    response_model=list[CustomFieldDefinitionResponse],
    status_code=status.HTTP_200_OK,
    summary="List custom field definitions for the current tenant",
)
async def list_custom_field_definitions(
    entity_type: str | None = Query(default=None, pattern="^(account|contact|deal)$"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    stmt = select(CustomFieldDefinition).where(CustomFieldDefinition.tenant_id == current_user.tenant_id)
    if entity_type:
        stmt = stmt.where(CustomFieldDefinition.entity_type == entity_type)
    stmt = stmt.order_by(CustomFieldDefinition.created_at.asc())
    return list((await db.scalars(stmt)).all())


@custom_fields_router.post(
    "",
    response_model=CustomFieldDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new dynamic custom field definition for accounts, contacts, or deals",
)
async def create_custom_field_definition(
    payload: CustomFieldDefinitionCreate,
    current_user: AuthenticatedUser = Depends(require_roles(_ADMIN_MANAGER_ROLES)),
    db: AsyncSession = Depends(get_tenant_db),
):
    if payload.field_type in {"select", "multi_select"} and not payload.allowed_values:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Custom fields of type 'select' or 'multi_select' must define non-empty 'allowed_values'.",
        )

    defn = CustomFieldDefinition(
        id=uuid.uuid4(),
        tenant_id=current_user.tenant_id,
        entity_type=payload.entity_type,
        field_key=payload.field_key.strip(),
        label=payload.label.strip(),
        field_type=payload.field_type,
        is_required=payload.is_required,
        min_stage_position=payload.min_stage_position,
        allowed_values=payload.allowed_values,
        is_indexed=payload.is_indexed,
    )
    db.add(defn)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Custom field '{payload.field_key}' already exists for "
                f"entity '{payload.entity_type}' in this tenant."
            ),
        ) from exc

    await record_entity_audit(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="custom_field",
        entity_id=defn.id,
        action="CREATE",
        actor_user_id=current_user.id,
        changes={
            "entity_type": payload.entity_type,
            "field_key": defn.field_key,
            "field_type": defn.field_type,
            "is_required": defn.is_required,
        },
    )
    await db.flush()
    await db.refresh(defn)
    return defn


@custom_fields_router.delete(
    "/{field_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a custom field definition",
)
async def delete_custom_field_definition(
    field_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(require_roles(_ADMIN_MANAGER_ROLES)),
    db: AsyncSession = Depends(get_tenant_db),
):
    defn = await db.scalar(
        select(CustomFieldDefinition).where(
            CustomFieldDefinition.id == field_id,
            CustomFieldDefinition.tenant_id == current_user.tenant_id,
        )
    )
    if not defn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom field definition not found.")

    await db.delete(defn)
    await db.flush()
    return None


@interactions_router.post(
    "",
    response_model=InteractionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log an interaction (call, email, meeting, note) with automatic hierarchical account roll-up",
)
async def create_interaction(
    payload: InteractionCreate,
    current_user: AuthenticatedUser = Depends(require_roles(_WRITE_ROLES)),
    db: AsyncSession = Depends(get_tenant_db),
):
    occurred = payload.occurred_at or datetime.now(UTC)
    resolved_account_id, resolved_deal_id, resolved_contact_id = await resolve_interaction_hierarchy(
        db,
        tenant_id=current_user.tenant_id,
        account_id=payload.account_id,
        deal_id=payload.deal_id,
        contact_id=payload.contact_id,
        occurred_at=occurred,
        direction=payload.direction,
    )

    interaction = Interaction(
        id=uuid.uuid4(),
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        contact_id=resolved_contact_id,
        account_id=resolved_account_id,
        deal_id=resolved_deal_id,
        type=payload.type,
        direction=payload.direction,
        subject=payload.subject.strip(),
        content_body=payload.content_body.strip(),
        occurred_at=occurred,
        metadata_=payload.metadata,
    )
    db.add(interaction)
    db.add(
        OutboxEvent(
            id=uuid.uuid4(),
            tenant_id=current_user.tenant_id,
            aggregate_type="interaction",
            aggregate_id=interaction.id,
            event_type="InteractionLogged",
            payload={
                "interaction_id": str(interaction.id),
                "type": interaction.type,
                "direction": interaction.direction,
                "account_id": str(resolved_account_id) if resolved_account_id else None,
                "deal_id": str(resolved_deal_id) if resolved_deal_id else None,
                "contact_id": str(resolved_contact_id) if resolved_contact_id else None,
                "logged_by": str(current_user.id),
            },
            status="pending",
        )
    )
    await db.flush()
    await db.refresh(interaction)
    return interaction


@audit_logs_router.get(
    "",
    response_model=list[EntityAuditLogResponse],
    status_code=status.HTTP_200_OK,
    summary="List system entity audit trail entries for compliance and change diagnostics",
)
async def list_entity_audit_logs(
    entity_type: str | None = Query(default=None),
    entity_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(require_roles(_ADMIN_MANAGER_ROLES)),
    db: AsyncSession = Depends(get_tenant_db),
):
    stmt = select(EntityAuditLog).where(EntityAuditLog.tenant_id == current_user.tenant_id)
    if entity_type:
        stmt = stmt.where(EntityAuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(EntityAuditLog.entity_id == entity_id)
    stmt = stmt.order_by(EntityAuditLog.created_at.desc()).limit(limit)
    return list((await db.scalars(stmt)).all())
