"""
Authentication API Router: Workspace Registration, Login, Refresh Rotation & Logout.
"""

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_raw_db
from src.core.dependencies import get_current_user, get_tenant_db
from src.core.rate_limit import rate_limit
from src.models.entities import Tenant
from src.schemas.crm import (
    AuthenticatedUser,
    AuthTokenResponse,
    LoginRequest,
    RefreshRequest,
    RegisterWorkspaceRequest,
    UserInfoResponse,
)
from src.services.auth_service import (
    AmbiguousTenantError,
    AuthenticationError,
    TokenReuseDetectedError,
    WorkspaceConflictError,
    authenticate_user,
    register_workspace,
    revoke_refresh_family,
    rotate_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["Authentication & Identity"])

REFRESH_COOKIE_NAME = "crm_refresh_token"
REFRESH_COOKIE_PATH = f"{settings.API_V1_STR}/auth"


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )


@router.post(
    "/register",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("auth_register", limit=10, window_seconds=60))],
    summary="Provision a new multi-tenant workspace, default pipeline, and admin account",
)
async def register(
    payload: RegisterWorkspaceRequest,
    response: Response,
    db: AsyncSession = Depends(get_raw_db),
):
    try:
        tokens = await register_workspace(db, payload)
    except WorkspaceConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    _set_refresh_cookie(response, tokens.refresh_token)
    return tokens


@router.post(
    "/login",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit("auth_login", limit=20, window_seconds=60))],
    summary="Authenticate user and issue JWT access token + HttpOnly rotated refresh cookie",
)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_raw_db),
):
    try:
        tokens = await authenticate_user(db, payload)
    except AmbiguousTenantError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    _set_refresh_cookie(response, tokens.refresh_token)
    return tokens


@router.post(
    "/refresh",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(rate_limit("auth_refresh", limit=30, window_seconds=60))],
    summary="Rotate refresh token family and issue a new access token",
)
async def refresh_session(
    response: Response,
    payload: RefreshRequest | None = None,
    crm_refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_raw_db),
):
    raw_token = (payload.refresh_token if payload and payload.refresh_token else None) or crm_refresh_token
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token cookie or payload.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        tokens = await rotate_refresh_token(db, raw_token)
    except TokenReuseDetectedError as exc:
        response.delete_cookie(key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except AuthenticationError as exc:
        response.delete_cookie(key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    _set_refresh_cookie(response, tokens.refresh_token)
    return tokens


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke active refresh token family and clear session cookie",
)
async def logout(
    response: Response,
    payload: RefreshRequest | None = None,
    crm_refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_raw_db),
):
    raw_token = (payload.refresh_token if payload and payload.refresh_token else None) or crm_refresh_token
    if raw_token:
        await revoke_refresh_family(db, raw_token)
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
    return None


@router.get(
    "/me",
    response_model=UserInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Return currently authenticated user and tenant context",
)
async def get_me(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    tenant = await db.scalar(select(Tenant).where(Tenant.id == current_user.tenant_id))
    return UserInfoResponse(
        id=current_user.id,
        tenant_id=current_user.tenant_id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        tenant_name=tenant.name if tenant else None,
        tenant_slug=tenant.slug if tenant else None,
    )
