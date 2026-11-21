"""
Communications & Email Synchronization API Router.
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_tenant_db, require_roles
from src.schemas.crm import AuthenticatedUser, EmailSyncIngestRequest, EmailSyncIngestResponse
from src.services.email_sync_service import ingest_synced_email

router = APIRouter(prefix="/communications", tags=["Email & Calendar Synchronization"])

_WRITE_ROLES = ["admin", "sales_manager", "sales_rep"]


@router.post(
    "/email-sync",
    response_model=EmailSyncIngestResponse,
    summary="Ingest synced email with RFC 5322 Message-ID deduplication, noise filtering & privacy guard",
)
async def sync_email_message(
    payload: EmailSyncIngestRequest,
    response: Response,
    current_user: AuthenticatedUser = Depends(require_roles(_WRITE_ROLES)),
    db: AsyncSession = Depends(get_tenant_db),
):
    result, is_new = await ingest_synced_email(db, current_user, payload)
    response.status_code = status.HTTP_201_CREATED if is_new else status.HTTP_200_OK
    return result
