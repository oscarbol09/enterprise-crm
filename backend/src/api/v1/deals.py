"""
Deals & Pipeline API Router: Creation, Stage Transition, Forecasting & Timeline.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_tenant_db, require_roles
from src.models.entities import Contact, Deal, Interaction, OutboxEvent, PipelineStage
from src.schemas.crm import (
    AuthenticatedUser,
    DealCreate,
    DealResponse,
    DealStageMoveRequest,
    InteractionResponse,
    PipelineStageResponse,
)
from src.services.embedding_service import upsert_entity_embedding
from src.services.pipeline_service import (
    apply_deal_stage_transition,
    compute_forecast_category,
    ensure_default_pipeline,
)

router = APIRouter(prefix="/deals", tags=["Deals & Sales Pipeline"])

_WRITE_ROLES = ["admin", "sales_manager", "sales_rep"]


@router.get(
    "",
    response_model=list[DealResponse],
    status_code=status.HTTP_200_OK,
    summary="List deals belonging to the current tenant",
)
async def list_deals(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    stmt = (
        select(Deal)
        .where(Deal.tenant_id == current_user.tenant_id)
        .order_by(Deal.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    deals = await db.scalars(stmt)
    return list(deals.all())


@router.post(
    "",
    response_model=DealResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new deal in a tenant pipeline stage",
)
async def create_deal(
    payload: DealCreate,
    current_user: AuthenticatedUser = Depends(require_roles(_WRITE_ROLES)),
    db: AsyncSession = Depends(get_tenant_db),
):
    stage = await db.scalar(
        select(PipelineStage).where(
            PipelineStage.id == payload.stage_id,
            PipelineStage.tenant_id == current_user.tenant_id,
        )
    )
    if not stage:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Stage {payload.stage_id} does not exist in this tenant.",
        )

    if payload.contact_id:
        contact_exists = await db.scalar(
            select(Contact.id).where(
                Contact.id == payload.contact_id,
                Contact.tenant_id == current_user.tenant_id,
            )
        )
        if not contact_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contact {payload.contact_id} not found in this tenant.",
            )

    forecast = compute_forecast_category(
        win_probability=stage.default_probability,
        is_closed_won=stage.is_closed_won,
        is_closed_lost=stage.is_closed_lost,
    )

    new_deal = Deal(
        id=uuid.uuid4(),
        tenant_id=current_user.tenant_id,
        pipeline_id=stage.pipeline_id,
        stage_id=stage.id,
        account_id=payload.account_id,
        contact_id=payload.contact_id,
        owner_id=current_user.id,
        title=payload.title,
        amount=payload.amount,
        currency=payload.currency,
        expected_close_date=payload.expected_close_date,
        forecast_category=forecast,
        win_probability=stage.default_probability,
        is_won=stage.is_closed_won,
        is_lost=stage.is_closed_lost,
    )
    db.add(new_deal)
    await db.flush()

    await upsert_entity_embedding(
        session=db,
        tenant_id=current_user.tenant_id,
        entity_type="deal",
        entity_id=new_deal.id,
        text_content=f"{new_deal.title} ({new_deal.currency} {new_deal.amount}) - Stage: {stage.name}",
    )

    db.add(
        OutboxEvent(
            id=uuid.uuid4(),
            tenant_id=current_user.tenant_id,
            aggregate_type="deal",
            aggregate_id=new_deal.id,
            event_type="DealCreated",
            payload={
                "deal_id": str(new_deal.id),
                "title": new_deal.title,
                "amount": float(new_deal.amount),
                "stage_id": str(stage.id),
                "created_by": str(current_user.id),
            },
            status="pending",
        )
    )
    await db.flush()
    await db.refresh(new_deal)
    return new_deal


@router.get(
    "/stages",
    response_model=list[PipelineStageResponse],
    status_code=status.HTTP_200_OK,
    summary="List pipeline stages for current tenant",
)
async def list_pipeline_stages(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    stmt = (
        select(PipelineStage)
        .where(PipelineStage.tenant_id == current_user.tenant_id)
        .order_by(PipelineStage.position.asc())
    )
    stages = await db.scalars(stmt)
    return list(stages.all())


@router.post(
    "/pipelines/bootstrap",
    response_model=list[PipelineStageResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Provision default pipeline stages if the tenant has none configured",
)
async def bootstrap_pipeline(
    current_user: AuthenticatedUser = Depends(require_roles(["admin", "sales_manager"])),
    db: AsyncSession = Depends(get_tenant_db),
):
    return await ensure_default_pipeline(db, current_user.tenant_id)


@router.get(
    "/{deal_id}/interactions",
    response_model=list[InteractionResponse],
    status_code=status.HTTP_200_OK,
    summary="List chronological interactions associated with a deal",
)
async def list_deal_interactions(
    deal_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    deal_exists = await db.scalar(
        select(Deal.id).where(Deal.id == deal_id, Deal.tenant_id == current_user.tenant_id)
    )
    if not deal_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Deal {deal_id} not found.")

    interactions = await db.scalars(
        select(Interaction)
        .where(Interaction.deal_id == deal_id, Interaction.tenant_id == current_user.tenant_id)
        .order_by(Interaction.occurred_at.desc())
        .limit(50)
    )
    return list(interactions.all())


@router.post(
    "/{deal_id}/move-stage",
    response_model=DealResponse,
    status_code=status.HTTP_200_OK,
    summary="Move a deal to a new pipeline stage with probability sync and audit event",
)
async def move_deal_stage(
    deal_id: uuid.UUID,
    payload: DealStageMoveRequest,
    current_user: AuthenticatedUser = Depends(require_roles(_WRITE_ROLES)),
    db: AsyncSession = Depends(get_tenant_db),
):
    deal = await db.scalar(select(Deal).where(Deal.id == deal_id, Deal.tenant_id == current_user.tenant_id))
    if not deal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Deal with ID {deal_id} not found."
        )

    target_stage = await db.scalar(
        select(PipelineStage).where(
            PipelineStage.id == payload.new_stage_id,
            PipelineStage.pipeline_id == deal.pipeline_id,
            PipelineStage.tenant_id == current_user.tenant_id,
        )
    )
    if not target_stage:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Target stage ID {payload.new_stage_id} is invalid or does not belong to pipeline {deal.pipeline_id}.",
        )

    if target_stage.is_closed_lost and not (payload.loss_reason and payload.loss_reason.strip()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A 'loss_reason' is strictly mandatory when transitioning a deal to a Closed Lost stage.",
        )

    return await apply_deal_stage_transition(
        session=db,
        deal=deal,
        target_stage=target_stage,
        actor_user_id=current_user.id,
        actor_name=current_user.full_name,
        loss_reason=payload.loss_reason.strip() if payload.loss_reason else None,
        notes=payload.notes,
    )
