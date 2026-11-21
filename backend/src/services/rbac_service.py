"""
Hierarchical & Ownership Role-Based Access Control (RBAC) Service.
Supports workspace-configurable visibility scopes: 'all', 'team', and 'owner_only'.
"""

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.entities import Tenant, User
from src.schemas.crm import AuthenticatedUser


async def get_tenant_settings(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, Any]:
    settings_json = await session.scalar(select(Tenant.settings).where(Tenant.id == tenant_id))
    return dict(settings_json or {})


async def get_visible_owner_ids(
    session: AsyncSession,
    current_user: AuthenticatedUser,
) -> set[uuid.UUID] | None:
    """
    Determines which `owner_id` UUIDs `current_user` is permitted to read.
    Returns `None` when the user has unrestricted tenant-wide read access ('admin', 'sales_manager',
    or when workspace `record_visibility_mode` is 'all').
    """
    if current_user.role in ("admin", "sales_manager"):
        return None

    cfg = await get_tenant_settings(session, current_user.tenant_id)
    mode = cfg.get("record_visibility_mode", "all")

    if mode == "owner_only":
        return {current_user.id}

    if mode == "team":
        user_team_id = current_user.team_id
        if user_team_id is None:
            user_team_id = await session.scalar(
                select(User.team_id).where(
                    User.id == current_user.id,
                    User.tenant_id == current_user.tenant_id,
                )
            )
        if user_team_id is None:
            return {current_user.id}
        team_members = list(
            (
                await session.scalars(
                    select(User.id).where(
                        User.tenant_id == current_user.tenant_id,
                        User.team_id == user_team_id,
                        User.is_active.is_(True),
                    )
                )
            ).all()
        )
        return set(team_members) | {current_user.id}

    return None


async def verify_record_access(
    session: AsyncSession,
    current_user: AuthenticatedUser,
    record_owner_id: uuid.UUID,
    *,
    require_write: bool = False,
) -> None:
    """
    Enforces read and write ownership boundaries for non-admin/non-manager roles.
    """
    if current_user.role in ("admin", "sales_manager"):
        return

    visible_owners = await get_visible_owner_ids(session, current_user)
    if visible_owners is not None and record_owner_id not in visible_owners:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not have visibility or ownership rights for this record.",
        )

    if require_write:
        cfg = await get_tenant_settings(session, current_user.tenant_id)
        if cfg.get("enforce_owner_write_guard", False) and record_owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Only the record owner or a manager can modify this record.",
            )
