"""
FastAPI Dependencies: JWT Authentication, Active User Validation, RBAC & Forced RLS Binding.
"""

import uuid
from collections.abc import AsyncGenerator, Callable

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import AsyncSessionLocal, set_tenant_rls_context
from src.core.security import decode_access_token
from src.models.entities import Tenant, User
from src.schemas.crm import AuthenticatedUser

security_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security_scheme),
) -> AuthenticatedUser:
    """
    Decodes and validates the Bearer JWT access token without hitting the database yet.
    """
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user_id_str = payload.get("sub")
    tenant_id_str = payload.get("tenant_id")
    role_str = payload.get("role")

    if not user_id_str or not tenant_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token claims: missing sub or tenant_id",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_uuid = uuid.UUID(user_id_str)
        tenant_uuid = uuid.UUID(tenant_id_str)
        team_uuid = uuid.UUID(payload["team_id"]) if payload.get("team_id") else None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed UUID in token claims",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return AuthenticatedUser(
        id=user_uuid,
        tenant_id=tenant_uuid,
        email=payload.get("email") or "user@enterprise.io",
        full_name=payload.get("name") or "CRM User",
        role=role_str or "sales_rep",
        team_id=team_uuid,
    )


async def get_tenant_db(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AsyncGenerator[AsyncSession, None]:
    """
    CRITICAL MULTI-TENANT ISOLATION LAYER:
    1. Binds `app.current_tenant_id` using `set_config(..., true)` for PostgreSQL Forced RLS.
    2. Verifies the caller's user and tenant remain active in PostgreSQL (prevents revoked-user JWT reuse).
    """
    async with AsyncSessionLocal() as session:
        try:
            await set_tenant_rls_context(session, current_user.tenant_id)

            active_check = await session.execute(
                select(User.is_active, User.role, Tenant.is_active)
                .join(Tenant, Tenant.id == User.tenant_id)
                .where(User.id == current_user.id, User.tenant_id == current_user.tenant_id)
            )
            row = active_check.first()
            if row is None or not row[0] or not row[2]:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User account or tenant workspace is inactive or no longer exists",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def require_roles(allowed_roles: list[str]) -> Callable:
    """RBAC Guard enforcing minimum role membership."""

    def role_checker(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Operation requires one of the following roles: {', '.join(allowed_roles)}",
            )
        return current_user

    return role_checker
