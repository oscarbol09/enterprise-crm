"""
Authentication & Session Service: Workspace Registration, Login, Refresh Token Rotation,
and Reuse Attack Detection under PostgreSQL Forced RLS.
"""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import set_tenant_rls_context
from src.core.security import (
    create_access_token,
    generate_refresh_token,
    get_password_hash_async,
    hash_token,
    verify_password_async,
)
from src.models.entities import RefreshToken, Tenant, User
from src.schemas.crm import AuthTokenResponse, LoginRequest, RegisterWorkspaceRequest, UserInfoResponse
from src.services.pipeline_service import ensure_default_pipeline

logger = structlog.get_logger(__name__)


class AuthenticationError(Exception):
    """Raised when credentials or session tokens are invalid."""


class WorkspaceConflictError(Exception):
    """Raised when tenant slug or email conflicts with existing records."""


class AmbiguousTenantError(Exception):
    """Raised when an email exists in multiple tenants and tenant_slug was omitted."""


class TokenReuseDetectedError(AuthenticationError):
    """Raised when a revoked refresh token is replayed (possible session hijack)."""


def _is_postgres(session: AsyncSession) -> bool:
    bind = session.get_bind()
    return bind is not None and bind.dialect.name == "postgresql"


def _utc_expiry(days: int) -> datetime:
    return datetime.now(UTC) + timedelta(days=days)


async def _issue_token_pair(
    session: AsyncSession,
    user: User,
    tenant: Tenant,
    family_id: uuid.UUID | None = None,
) -> AuthTokenResponse:
    access_token = create_access_token(
        user_id=str(user.id),
        tenant_id=str(tenant.id),
        role=user.role,
        email=user.email,
        full_name=user.full_name,
        team_id=str(user.team_id) if user.team_id else None,
    )

    raw_refresh = generate_refresh_token()
    refresh_record = RefreshToken(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        user_id=user.id,
        family_id=family_id or uuid.uuid4(),
        token_hash=hash_token(raw_refresh),
        is_revoked=False,
        expires_at=_utc_expiry(settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    session.add(refresh_record)
    await session.flush()

    return AuthTokenResponse(
        access_token=access_token,
        token_type="bearer",  # noqa: S106
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        refresh_token=raw_refresh,
        user=UserInfoResponse(
            id=user.id,
            tenant_id=tenant.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            tenant_name=tenant.name,
            tenant_slug=tenant.slug,
        ),
    )


async def register_workspace(session: AsyncSession, req: RegisterWorkspaceRequest) -> AuthTokenResponse:
    normalized_slug = req.tenant_slug.strip().lower()
    normalized_email = req.admin_email.strip().lower()

    existing_tenant = await session.scalar(select(Tenant).where(Tenant.slug == normalized_slug))
    if existing_tenant:
        raise WorkspaceConflictError(f"Workspace slug '{normalized_slug}' is already registered.")

    tenant = Tenant(
        id=uuid.uuid4(),
        name=req.tenant_name.strip(),
        slug=normalized_slug,
        plan_tier="enterprise",
        is_active=True,
    )
    session.add(tenant)
    await session.flush()

    # Bind Forced RLS context immediately before inserting tenant-scoped records
    await set_tenant_rls_context(session, tenant.id)

    password_hash = await get_password_hash_async(req.password)
    admin_user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=normalized_email,
        password_hash=password_hash,
        full_name=req.admin_full_name.strip(),
        role="admin",
        is_active=True,
    )
    session.add(admin_user)
    await session.flush()

    await ensure_default_pipeline(session, tenant.id)
    return await _issue_token_pair(session, admin_user, tenant)


async def _resolve_tenant_for_login(
    session: AsyncSession,
    email: str,
    tenant_slug: str | None,
) -> Tenant:
    if tenant_slug:
        tenant = await session.scalar(
            select(Tenant).where(Tenant.slug == tenant_slug.strip().lower(), Tenant.is_active == True)  # noqa: E712
        )
        if not tenant:
            raise AuthenticationError("Invalid credentials or inactive workspace.")
        return tenant

    if _is_postgres(session):
        rows = (
            await session.execute(
                text("SELECT tenant_id, tenant_slug, tenant_name FROM lookup_user_tenants_by_email(:email)"),
                {"email": email},
            )
        ).all()
        if not rows:
            raise AuthenticationError("Invalid email or password.")
        if len(rows) > 1:
            raise AmbiguousTenantError(
                "Multiple workspaces found for this email. Please specify your workspace slug."
            )
        tenant_id = rows[0][0]
        tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id, Tenant.is_active == True))  # noqa: E712
        if not tenant:
            raise AuthenticationError("Workspace is inactive.")
        return tenant

    # SQLite fallback for hermetic unit tests
    stmt = (
        select(Tenant)
        .join(User, User.tenant_id == Tenant.id)
        .where(User.email == email, User.is_active == True, Tenant.is_active == True)  # noqa: E712
    )
    tenants = list((await session.scalars(stmt)).all())
    if not tenants:
        raise AuthenticationError("Invalid email or password.")
    if len(tenants) > 1:
        raise AmbiguousTenantError(
            "Multiple workspaces found for this email. Please specify your workspace slug."
        )
    return tenants[0]


async def authenticate_user(session: AsyncSession, req: LoginRequest) -> AuthTokenResponse:
    normalized_email = req.email.strip().lower()
    tenant = await _resolve_tenant_for_login(session, normalized_email, req.tenant_slug)

    await set_tenant_rls_context(session, tenant.id)

    user = await session.scalar(
        select(User).where(
            User.tenant_id == tenant.id,
            User.email == normalized_email,
            User.is_active == True,  # noqa: E712
        )
    )
    if not user:
        raise AuthenticationError("Invalid email or password.")

    valid = await verify_password_async(req.password, user.password_hash)
    if not valid:
        raise AuthenticationError("Invalid email or password.")

    return await _issue_token_pair(session, user, tenant)


async def _find_refresh_token_record(
    session: AsyncSession, token_hash: str
) -> tuple[RefreshToken | None, uuid.UUID | None]:
    if _is_postgres(session):
        tenant_id = await session.scalar(
            text("SELECT lookup_refresh_token_tenant(:token_hash)"),
            {"token_hash": token_hash},
        )
        if not tenant_id:
            return None, None
        await set_tenant_rls_context(session, tenant_id)

    record = await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if not record:
        return None, None
    return record, record.tenant_id


async def rotate_refresh_token(session: AsyncSession, raw_refresh_token: str) -> AuthTokenResponse:
    token_hash = hash_token(raw_refresh_token)
    record, tenant_id = await _find_refresh_token_record(session, token_hash)

    if not record or not tenant_id:
        raise AuthenticationError("Invalid refresh token.")

    if record.is_revoked:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == record.family_id, RefreshToken.tenant_id == tenant_id)
            .values(is_revoked=True)
        )
        await session.commit()
        logger.warning(
            "Refresh token reuse detected; revoked entire token family",
            user_id=str(record.user_id),
            tenant_id=str(tenant_id),
            family_id=str(record.family_id),
        )
        raise TokenReuseDetectedError("Token reuse detected. All sessions in this family have been revoked.")

    now = datetime.now(UTC)
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        record.is_revoked = True
        await session.flush()
        raise AuthenticationError("Refresh token has expired.")

    user = await session.scalar(select(User).where(User.id == record.user_id, User.is_active == True))  # noqa: E712
    tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id, Tenant.is_active == True))  # noqa: E712
    if not user or not tenant:
        raise AuthenticationError("User or workspace is inactive.")

    record.is_revoked = True
    await session.flush()
    return await _issue_token_pair(session, user, tenant, family_id=record.family_id)


async def revoke_refresh_family(session: AsyncSession, raw_refresh_token: str) -> None:
    token_hash = hash_token(raw_refresh_token)
    record, tenant_id = await _find_refresh_token_record(session, token_hash)
    if record and tenant_id:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == record.family_id, RefreshToken.tenant_id == tenant_id)
            .values(is_revoked=True)
        )
        await session.flush()
