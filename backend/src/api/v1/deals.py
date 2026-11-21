"""
Deals & Pipeline API Router: Creation, Custom Fields Validation, B2B Buying Committee Participants,
Stage Transition, SCD Type 2 Stage History, Forecasting & Timeline.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user, get_tenant_db, require_roles
from src.models.entities import (
    Contact,
    Deal,
    DealParticipant,
    DealStageHistory,
    Interaction,
    OutboxEvent,
    PipelineStage,
)
from src.schemas.crm import (
    AuthenticatedUser,
    DealCreate,
    DealParticipantCreate,
    DealParticipantResponse,
    DealPlaybookResponse,
    DealResponse,
    DealStageHistoryResponse,
    DealStageMoveRequest,
    DealUpdate,
    InteractionResponse,
    PipelineStageResponse,
)
from src.services.audit_service import (
    apply_sql_keyset_cursor,
    record_entity_audit,
    slice_keyset_page,
)
from src.services.currency_service import (
    compute_normalized_usd_amount,
    generate_deal_rep_playbook,
    resolve_exchange_rate_to_usd,
)
from src.services.custom_fields_service import (
    matches_custom_field_filter,
    validate_entity_custom_fields,
)
from src.services.embedding_service import upsert_entity_embedding
from src.services.pipeline_service import (
    apply_deal_stage_transition,
    compute_forecast_category,
    ensure_default_pipeline,
)
from src.services.rbac_service import get_visible_owner_ids, verify_record_access

router = APIRouter(prefix="/deals", tags=["Deals & Sales Pipeline"])

_WRITE_ROLES = ["admin", "sales_manager", "sales_rep"]


@router.get(
    "",
    response_model=list[DealResponse],
    status_code=status.HTTP_200_OK,
    summary="List deals belonging to the current tenant with RBAC and custom field filtering",
)
async def list_deals(
    response: Response,
    q: str | None = Query(default=None, max_length=120),
    cf_key: str | None = Query(default=None, max_length=100),
    cf_value: str | None = Query(default=None, max_length=255),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    stmt = select(Deal).where(
        Deal.tenant_id == current_user.tenant_id,
        Deal.deleted_at.is_(None),
    )

    visible_owners = await get_visible_owner_ids(db, current_user)
    if visible_owners is not None:
        stmt = stmt.where(Deal.owner_id.in_(visible_owners))

    if q and q.strip():
        stmt = stmt.where(Deal.title.ilike(f"%{q.strip()}%"))

    stmt = apply_sql_keyset_cursor(stmt, Deal, cursor)
    stmt = stmt.order_by(Deal.created_at.desc(), Deal.id.desc())
    if not cf_key:
        stmt = stmt.limit(limit + 1)

    rows = list((await db.scalars(stmt)).all())
    if cf_key:
        rows = [d for d in rows if matches_custom_field_filter(d.metadata_, cf_key, cf_value)]

    page, next_cursor = slice_keyset_page(rows, limit)
    if next_cursor:
        response.headers["X-Next-Cursor"] = next_cursor
    return page


@router.post(
    "",
    response_model=DealResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new deal with custom field validation, SCD Type 2 initial stage history, and primary participant",
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

    resolved_account_id = payload.account_id
    resolved_source_channel = payload.source_channel.lower() if payload.source_channel else None
    if payload.contact_id:
        contact = await db.scalar(
            select(Contact).where(
                Contact.id == payload.contact_id,
                Contact.tenant_id == current_user.tenant_id,
                Contact.deleted_at.is_(None),
            )
        )
        if not contact:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contact {payload.contact_id} not found in this tenant.",
            )
        if resolved_account_id is None and contact.account_id is not None:
            resolved_account_id = contact.account_id
        if resolved_source_channel is None and contact.source_channel:
            resolved_source_channel = contact.source_channel

    validated_metadata = await validate_entity_custom_fields(
        db,
        current_user.tenant_id,
        "deal",
        payload.metadata,
        stage_position=stage.position,
    )

    forecast = compute_forecast_category(
        win_probability=stage.default_probability,
        is_closed_won=stage.is_closed_won,
        is_closed_lost=stage.is_closed_lost,
    )

    fx_rate = resolve_exchange_rate_to_usd(payload.currency, payload.exchange_rate_to_usd)
    normalized_usd = compute_normalized_usd_amount(payload.amount, fx_rate)

    now = datetime.now(UTC)
    new_deal = Deal(
        id=uuid.uuid4(),
        tenant_id=current_user.tenant_id,
        pipeline_id=stage.pipeline_id,
        stage_id=stage.id,
        account_id=resolved_account_id,
        contact_id=payload.contact_id,
        owner_id=current_user.id,
        title=payload.title,
        amount=payload.amount,
        currency=payload.currency,
        exchange_rate_to_usd=fx_rate,
        normalized_amount_usd=normalized_usd,
        expected_close_date=payload.expected_close_date,
        forecast_category=forecast,
        win_probability=stage.default_probability,
        is_won=stage.is_closed_won,
        is_lost=stage.is_closed_lost,
        source_channel=resolved_source_channel,
        metadata_=validated_metadata,
        stage_entered_at=now,
        closed_at=now if (stage.is_closed_won or stage.is_closed_lost) else None,
    )
    db.add(new_deal)
    await db.flush()

    # 1. Open initial SCD Type 2 Stage History entry
    db.add(
        DealStageHistory(
            id=uuid.uuid4(),
            tenant_id=current_user.tenant_id,
            deal_id=new_deal.id,
            from_stage_id=None,
            to_stage_id=stage.id,
            amount_at_transition=new_deal.amount,
            win_probability_at_transition=new_deal.win_probability,
            expected_close_date_at_transition=new_deal.expected_close_date,
            changed_by=current_user.id,
            entered_at=now,
            exited_at=None,
            duration_seconds=None,
        )
    )

    # 2. Auto-enroll primary contact in Deal Buying Committee as 'champion'
    if payload.contact_id:
        db.add(
            DealParticipant(
                id=uuid.uuid4(),
                tenant_id=current_user.tenant_id,
                deal_id=new_deal.id,
                contact_id=payload.contact_id,
                buying_role="champion",
                is_primary=True,
                notes="Primary deal contact",
            )
        )

    await upsert_entity_embedding(
        session=db,
        tenant_id=current_user.tenant_id,
        entity_type="deal",
        entity_id=new_deal.id,
        text_content=f"{new_deal.title} ({new_deal.currency} {new_deal.amount}) - Stage: {stage.name}",
    )

    await record_entity_audit(
        db,
        tenant_id=current_user.tenant_id,
        entity_type="deal",
        entity_id=new_deal.id,
        action="CREATE",
        actor_user_id=current_user.id,
        changes={
            "title": new_deal.title,
            "amount_decimal": str(new_deal.amount),
            "stage_id": str(stage.id),
        },
    )

    decimal_amount = Decimal(str(new_deal.amount)).quantize(Decimal("0.01"))
    amount_cents = int((decimal_amount * Decimal("100")).to_integral_value())

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
                "amount": str(decimal_amount),
                "amount_decimal": str(decimal_amount),
                "amount_cents": amount_cents,
                "currency": new_deal.currency,
                "stage_id": str(stage.id),
                "created_by": str(current_user.id),
            },
            status="pending",
        )
    )
    await db.flush()
    await db.refresh(new_deal)
    return new_deal


@router.patch(
    "/{deal_id}",
    response_model=DealResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a deal, validating custom fields and tracking expected_close_date slippage",
)
async def update_deal(
    deal_id: uuid.UUID,
    payload: DealUpdate,
    current_user: AuthenticatedUser = Depends(require_roles(_WRITE_ROLES)),
    db: AsyncSession = Depends(get_tenant_db),
):
    deal = await db.scalar(
        select(Deal).where(
            Deal.id == deal_id,
            Deal.tenant_id == current_user.tenant_id,
            Deal.deleted_at.is_(None),
        )
    )
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Deal {deal_id} not found.")

    await verify_record_access(db, current_user, deal.owner_id, require_write=True)

    updates = payload.model_dump(exclude_unset=True)
    if "exchange_rate_to_usd" in updates and (deal.is_won or deal.is_lost):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot modify historical exchange rate on a closed deal.",
        )

    current_stage = await db.scalar(
        select(PipelineStage).where(
            PipelineStage.id == deal.stage_id,
            PipelineStage.tenant_id == current_user.tenant_id,
        )
    )
    if "metadata" in updates:
        raw_meta = updates.pop("metadata")
        deal.metadata_ = await validate_entity_custom_fields(
            db,
            current_user.tenant_id,
            "deal",
            raw_meta,
            is_partial=True,
            existing_metadata=deal.metadata_,
            stage_position=current_stage.position if current_stage else None,
        )

    if (
        "expected_close_date" in updates
        and updates["expected_close_date"] is not None
        and deal.expected_close_date is not None
        and updates["expected_close_date"] > deal.expected_close_date
    ):
        deal.close_date_push_count += 1

    for field, value in updates.items():
        setattr(deal, field, value)

    if "currency" in updates and "exchange_rate_to_usd" not in updates:
        deal.exchange_rate_to_usd = resolve_exchange_rate_to_usd(deal.currency, None)
    elif "exchange_rate_to_usd" in updates and updates["exchange_rate_to_usd"] is not None:
        deal.exchange_rate_to_usd = resolve_exchange_rate_to_usd(
            deal.currency, updates["exchange_rate_to_usd"]
        )

    deal.normalized_amount_usd = compute_normalized_usd_amount(deal.amount, deal.exchange_rate_to_usd)

    await db.flush()
    await db.refresh(deal)
    return deal


@router.get(
    "/{deal_id}/playbook",
    response_model=DealPlaybookResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate stage-tailored follow-up draft and recommended actions for the sales rep",
)
async def get_deal_playbook(
    deal_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    deal = await db.scalar(
        select(Deal).where(
            Deal.id == deal_id,
            Deal.tenant_id == current_user.tenant_id,
            Deal.deleted_at.is_(None),
        )
    )
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Deal {deal_id} not found.")

    stage = await db.scalar(
        select(PipelineStage).where(
            PipelineStage.id == deal.stage_id,
            PipelineStage.tenant_id == current_user.tenant_id,
        )
    )
    contact_first_name: str | None = None
    if deal.contact_id:
        contact_first_name = await db.scalar(
            select(Contact.first_name).where(
                Contact.id == deal.contact_id,
                Contact.tenant_id == current_user.tenant_id,
            )
        )

    playbook = generate_deal_rep_playbook(
        deal_title=deal.title,
        stage_name=stage.name if stage else "Pipeline",
        stage_position=stage.position if stage else 1,
        amount=deal.amount,
        currency=deal.currency,
        contact_first_name=contact_first_name,
    )
    return DealPlaybookResponse.model_validate(
        {
            **playbook,
            "deal_id": deal.id,
            "normalized_amount_usd": deal.normalized_amount_usd,
            "follow_up_email_subject": playbook["suggested_email_subject"],
            "follow_up_email_body": playbook["suggested_email_body"],
        }
    )


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


@router.post(
    "/{deal_id}/participants",
    response_model=DealParticipantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a stakeholder contact to the deal buying committee with an explicit role",
)
async def add_deal_participant(
    deal_id: uuid.UUID,
    payload: DealParticipantCreate,
    current_user: AuthenticatedUser = Depends(require_roles(_WRITE_ROLES)),
    db: AsyncSession = Depends(get_tenant_db),
):
    deal = await db.scalar(
        select(Deal).where(
            Deal.id == deal_id,
            Deal.tenant_id == current_user.tenant_id,
            Deal.deleted_at.is_(None),
        )
    )
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Deal {deal_id} not found.")

    await verify_record_access(db, current_user, deal.owner_id, require_write=True)

    contact = await db.scalar(
        select(Contact).where(
            Contact.id == payload.contact_id,
            Contact.tenant_id == current_user.tenant_id,
            Contact.deleted_at.is_(None),
        )
    )
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contact {payload.contact_id} not found.",
        )

    participant = DealParticipant(
        id=uuid.uuid4(),
        tenant_id=current_user.tenant_id,
        deal_id=deal.id,
        contact_id=contact.id,
        buying_role=payload.buying_role,
        is_primary=payload.is_primary,
        notes=payload.notes,
    )
    db.add(participant)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Contact is already a participant in this deal.",
        ) from exc

    await db.refresh(participant)
    return participant


@router.get(
    "/{deal_id}/participants",
    response_model=list[DealParticipantResponse],
    status_code=status.HTTP_200_OK,
    summary="List all buying committee participants for a deal",
)
async def list_deal_participants(
    deal_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    deal_exists = await db.scalar(
        select(Deal.id).where(
            Deal.id == deal_id,
            Deal.tenant_id == current_user.tenant_id,
            Deal.deleted_at.is_(None),
        )
    )
    if not deal_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Deal {deal_id} not found.")

    rows = await db.scalars(
        select(DealParticipant)
        .where(
            DealParticipant.tenant_id == current_user.tenant_id,
            DealParticipant.deal_id == deal_id,
        )
        .order_by(DealParticipant.is_primary.desc(), DealParticipant.created_at.asc())
    )
    return list(rows.all())


@router.get(
    "/{deal_id}/stage-history",
    response_model=list[DealStageHistoryResponse],
    status_code=status.HTTP_200_OK,
    summary="Fetch SCD Type 2 stage transition history with dwell time and point-in-time amounts",
)
async def get_deal_stage_history(
    deal_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db),
):
    deal_exists = await db.scalar(
        select(Deal.id).where(
            Deal.id == deal_id,
            Deal.tenant_id == current_user.tenant_id,
            Deal.deleted_at.is_(None),
        )
    )
    if not deal_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Deal {deal_id} not found.")

    rows = await db.scalars(
        select(DealStageHistory)
        .where(
            DealStageHistory.tenant_id == current_user.tenant_id,
            DealStageHistory.deal_id == deal_id,
        )
        .order_by(DealStageHistory.entered_at.asc())
    )
    return list(rows.all())


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
        select(Deal.id).where(
            Deal.id == deal_id,
            Deal.tenant_id == current_user.tenant_id,
            Deal.deleted_at.is_(None),
        )
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
    summary="Move a deal to a new pipeline stage with probability sync, SCD Type 2 history, and audit event",
)
async def move_deal_stage(
    deal_id: uuid.UUID,
    payload: DealStageMoveRequest,
    current_user: AuthenticatedUser = Depends(require_roles(_WRITE_ROLES)),
    db: AsyncSession = Depends(get_tenant_db),
):
    deal = await db.scalar(
        select(Deal).where(
            Deal.id == deal_id,
            Deal.tenant_id == current_user.tenant_id,
            Deal.deleted_at.is_(None),
        )
    )
    if not deal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Deal with ID {deal_id} not found."
        )

    await verify_record_access(db, current_user, deal.owner_id, require_write=True)

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
        loss_category=payload.loss_category,
        competitor_name=payload.competitor_name.strip() if payload.competitor_name else None,
        missing_feature_tag=payload.missing_feature_tag.strip() if payload.missing_feature_tag else None,
        notes=payload.notes,
    )
