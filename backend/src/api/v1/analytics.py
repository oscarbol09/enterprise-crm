"""
Revenue Intelligence, Forecasting & Attribution API Router.
"""

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import AuthenticatedUser, get_current_user, get_tenant_db, require_roles
from src.schemas.crm import (
    AttributionAnalyticsResponse,
    ForecastAnalyticsResponse,
    FunnelAnalyticsResponse,
    PipelineSnapshotRequest,
    PipelineSnapshotResponse,
    WaterfallBridgeResponse,
    WinLossAnalyticsResponse,
)
from src.services.analytics_service import (
    capture_pipeline_snapshot,
    compute_attribution_analytics,
    compute_forecast_analytics,
    compute_funnel_analytics,
    compute_waterfall_bridge,
    compute_win_loss_analytics,
)

analytics_router = APIRouter(prefix="/analytics", tags=["Revenue Intelligence & Forecasting"])


@analytics_router.get(
    "/forecast",
    response_model=ForecastAnalyticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Multi-currency USD forecast breakdown, sales velocity, quota coverage & risk radar",
)
async def get_forecast_analytics(
    quota_usd: Decimal | None = Query(default=None, gt=0),
    stale_days: int = Query(default=14, ge=1, le=365),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await compute_forecast_analytics(
        db,
        current_user.tenant_id,
        quota_usd=quota_usd,
        stale_days_threshold=stale_days,
    )


@analytics_router.get(
    "/funnel",
    response_model=FunnelAnalyticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Stage-to-stage conversion funnel and average dwell days from SCD Type 2 history",
)
async def get_funnel_analytics(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await compute_funnel_analytics(db, current_user.tenant_id)


@analytics_router.get(
    "/attribution",
    response_model=AttributionAnalyticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Acquisition source attribution contrasting lead volume against Closed-Won USD revenue",
)
async def get_attribution_analytics(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await compute_attribution_analytics(db, current_user.tenant_id)


@analytics_router.post(
    "/snapshots",
    response_model=PipelineSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Capture an idempotent point-in-time pipeline snapshot for Waterfall Bridge analysis",
)
async def create_pipeline_snapshot(
    payload: PipelineSnapshotRequest | None = None,
    current_user: AuthenticatedUser = Depends(require_roles(["admin", "sales_manager", "sales_rep"])),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await capture_pipeline_snapshot(
        db,
        current_user.tenant_id,
        snapshot_date=payload.snapshot_date if payload else None,
    )


@analytics_router.get(
    "/waterfall",
    response_model=WaterfallBridgeResponse,
    status_code=status.HTTP_200_OK,
    summary="Compute exact Decimal Pipeline Waterfall Bridge between two snapshot dates (T0 -> T1)",
)
async def get_pipeline_waterfall(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    resolved_to = to_date or date.today()
    resolved_from = from_date or (resolved_to - timedelta(days=30))
    return await compute_waterfall_bridge(
        db,
        current_user.tenant_id,
        from_date=resolved_from,
        to_date=resolved_to,
    )


@analytics_router.get(
    "/win-loss",
    response_model=WinLossAnalyticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Structured Win/Loss breakdown by loss category, competitor, and missing product feature",
)
async def get_win_loss_analytics(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await compute_win_loss_analytics(db, current_user.tenant_id)
