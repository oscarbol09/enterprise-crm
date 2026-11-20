"""
Tenant LLM Credentials API Router (BYOK - Bring Your Own Key Vault).
Enforces Admin RBAC, AES-256-GCM Encryption with tenant AAD, and Zero-Plaintext Exposure.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_tenant_db, require_roles
from src.core.security import encrypt_field
from src.models.entities import TenantLLMCredential
from src.schemas.crm import (
    AuthenticatedUser,
    LLMCredentialCreateRequest,
    LLMCredentialResponse,
)

router = APIRouter(prefix="/settings/llm-credentials", tags=["Settings - LLM Credentials (BYOK)"])


@router.post(
    "",
    response_model=LLMCredentialResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register or update a tenant's LLM API key (AES-256-GCM encrypted)",
)
async def register_tenant_llm_credential(
    payload: LLMCredentialCreateRequest,
    current_user: AuthenticatedUser = Depends(require_roles(["admin"])),
    db: AsyncSession = Depends(get_tenant_db),
):
    raw_key = payload.raw_api_key.strip()
    if len(raw_key) < 12:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="API key must contain at least 12 non-whitespace characters.",
        )

    aad = str(current_user.tenant_id).encode("utf-8")
    encrypted_bytes = encrypt_field(raw_key, associated_data=aad)
    last_four = raw_key[-4:]

    existing_cred = await db.scalar(
        select(TenantLLMCredential).where(
            TenantLLMCredential.tenant_id == current_user.tenant_id,
            TenantLLMCredential.provider == payload.provider,
        )
    )

    if existing_cred:
        existing_cred.encrypted_api_key = encrypted_bytes
        existing_cred.key_last_four = last_four
        existing_cred.is_active = True
        existing_cred.added_by = current_user.id
        await db.flush()
        await db.refresh(existing_cred)
        return existing_cred

    new_cred = TenantLLMCredential(
        id=uuid.uuid4(),
        tenant_id=current_user.tenant_id,
        provider=payload.provider,
        encrypted_api_key=encrypted_bytes,
        key_last_four=last_four,
        is_active=True,
        added_by=current_user.id,
    )
    db.add(new_cred)
    await db.flush()
    await db.refresh(new_cred)
    return new_cred


@router.get(
    "",
    response_model=list[LLMCredentialResponse],
    status_code=status.HTTP_200_OK,
    summary="List configured LLM credentials for the current tenant",
)
async def list_tenant_llm_credentials(
    current_user: AuthenticatedUser = Depends(require_roles(["admin"])),
    db: AsyncSession = Depends(get_tenant_db),
):
    result = await db.scalars(
        select(TenantLLMCredential)
        .where(TenantLLMCredential.tenant_id == current_user.tenant_id)
        .order_by(TenantLLMCredential.created_at.desc())
    )
    return list(result.all())


@router.delete(
    "/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-deactivate an LLM credential",
)
async def revoke_tenant_llm_credential(
    credential_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(require_roles(["admin"])),
    db: AsyncSession = Depends(get_tenant_db),
):
    cred = await db.scalar(
        select(TenantLLMCredential).where(
            TenantLLMCredential.id == credential_id,
            TenantLLMCredential.tenant_id == current_user.tenant_id,
        )
    )
    if not cred:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Credential with ID {credential_id} not found.",
        )

    cred.is_active = False
    await db.flush()
    return None
