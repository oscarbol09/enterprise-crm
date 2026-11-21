"""
CSV Import & Formula-Injection-Sanitized Export API Router.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import AuthenticatedUser, get_current_user, get_tenant_db, require_roles
from src.schemas.crm import CSVImportRequest, CSVImportResponse, ImportBatchRollbackResponse
from src.services.data_transfer_service import (
    export_entity_csv,
    import_contacts_csv,
    rollback_import_batch,
)

data_transfer_router = APIRouter(prefix="/data", tags=["Data Migration & Safe Export"])

_WRITE_ROLES = ["admin", "sales_manager", "sales_rep"]


@data_transfer_router.post(
    "/contacts/import",
    response_model=CSVImportResponse,
    status_code=status.HTTP_200_OK,
    summary="Import contacts from CSV with automatic header detection, Dry-Run preview, deduplication, and DLQ quarantine",
)
async def import_contacts_from_csv(
    payload: CSVImportRequest,
    current_user: AuthenticatedUser = Depends(require_roles(_WRITE_ROLES)),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await import_contacts_csv(
        db=db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        payload=payload,
    )


@data_transfer_router.post(
    "/imports/{batch_id}/rollback",
    response_model=ImportBatchRollbackResponse,
    status_code=status.HTTP_200_OK,
    summary="Atomically revert all accounts, contacts, and deals created in a CSV import batch",
)
async def rollback_csv_import_batch(
    batch_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(require_roles(_WRITE_ROLES)),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await rollback_import_batch(
        db=db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        batch_id=batch_id,
    )


@data_transfer_router.get(
    "/export/{entity}",
    status_code=status.HTTP_200_OK,
    summary="Export tenant contacts, deals, or accounts as Formula-Injection-sanitized CSV",
)
async def export_crm_entity_csv(
    entity: Literal["contacts", "deals", "accounts"],
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    csv_body = await export_entity_csv(
        db=db,
        tenant_id=current_user.tenant_id,
        entity=entity,
    )
    return Response(
        content=csv_body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="crm_{entity}_export.csv"',
            "X-Content-Type-Options": "nosniff",
        },
    )
