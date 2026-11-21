"""
Pipeline Domain Service: Default Stage Bootstrapping, Forecasting, SCD Type 2 Stage History & Stage Transitions.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.entities import (
    Deal,
    DealStageHistory,
    Interaction,
    OutboxEvent,
    Pipeline,
    PipelineStage,
    Task,
)
from src.schemas.crm import AuthenticatedUser
from src.services.audit_service import record_entity_audit, resolve_interaction_hierarchy
from src.services.custom_fields_service import validate_entity_custom_fields

DEFAULT_STAGES_SPEC: list[tuple[str, int, Decimal, bool, bool]] = [
    ("Prospección", 1, Decimal("0.10"), False, False),
    ("Calificación", 2, Decimal("0.30"), False, False),
    ("Propuesta", 3, Decimal("0.60"), False, False),
    ("Negociación", 4, Decimal("0.80"), False, False),
    ("Cierre Ganado", 5, Decimal("1.00"), True, False),
    ("Cierre Perdido", 6, Decimal("0.00"), False, True),
]


def compute_forecast_category(
    win_probability: Decimal,
    is_closed_won: bool,
    is_closed_lost: bool,
) -> str:
    if is_closed_won:
        return "closed"
    if is_closed_lost:
        return "omitted"
    if win_probability >= Decimal("0.80"):
        return "commit"
    if win_probability >= Decimal("0.50"):
        return "best_case"
    return "pipeline"


async def ensure_default_pipeline(session: AsyncSession, tenant_id: uuid.UUID) -> list[PipelineStage]:
    """
    Returns existing stages for the tenant or provisions the default 6-stage sales pipeline.
    """
    existing_stages = list(
        (
            await session.scalars(
                select(PipelineStage)
                .where(PipelineStage.tenant_id == tenant_id)
                .order_by(PipelineStage.position.asc())
            )
        ).all()
    )
    if existing_stages:
        return existing_stages

    pipeline = Pipeline(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="Pipeline Comercial Estándar",
        is_default=True,
    )
    session.add(pipeline)
    await session.flush()

    created_stages: list[PipelineStage] = []
    for name, position, prob, is_won, is_lost in DEFAULT_STAGES_SPEC:
        stage = PipelineStage(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            pipeline_id=pipeline.id,
            name=name,
            position=position,
            default_probability=prob,
            is_closed_won=is_won,
            is_closed_lost=is_lost,
        )
        session.add(stage)
        created_stages.append(stage)

    await session.flush()
    return created_stages


async def apply_deal_stage_transition(
    session: AsyncSession,
    deal: Deal,
    target_stage: PipelineStage,
    actor_user_id: uuid.UUID,
    actor_name: str,
    loss_reason: str | None = None,
    loss_category: str | None = None,
    competitor_name: str | None = None,
    missing_feature_tag: str | None = None,
    notes: str | None = None,
) -> Deal:
    """
    Applies a validated stage transition on a Deal, syncing probability, forecast category,
    SCD Type 2 stage history, hierarchical activity timeline interaction, system audit log,
    and transactional outbox event atomically.
    """
    now = datetime.now(UTC)
    previous_stage_id = deal.stage_id

    # 0. Enforce lazy stage-gated custom field requirements for target_stage.position
    await validate_entity_custom_fields(
        session,
        deal.tenant_id,
        "deal",
        None,
        is_partial=True,
        existing_metadata=deal.metadata_,
        stage_position=target_stage.position,
    )

    # 1. Close active SCD Type 2 stage history row(s)
    open_histories = list(
        (
            await session.scalars(
                select(DealStageHistory).where(
                    DealStageHistory.tenant_id == deal.tenant_id,
                    DealStageHistory.deal_id == deal.id,
                    DealStageHistory.exited_at.is_(None),
                )
            )
        ).all()
    )
    for hist in open_histories:
        hist.exited_at = now
        entered_aware = (
            hist.entered_at.replace(tzinfo=UTC) if hist.entered_at.tzinfo is None else hist.entered_at
        )
        hist.duration_seconds = max(0, int((now - entered_aware).total_seconds()))

    # 2. Mutate Deal state
    deal.stage_id = target_stage.id
    deal.win_probability = target_stage.default_probability
    deal.is_won = target_stage.is_closed_won
    deal.is_lost = target_stage.is_closed_lost
    deal.loss_reason = loss_reason if target_stage.is_closed_lost else None
    deal.loss_category = loss_category if target_stage.is_closed_lost else None
    deal.competitor_name = competitor_name if target_stage.is_closed_lost else None
    deal.missing_feature_tag = missing_feature_tag if target_stage.is_closed_lost else None
    deal.stage_entered_at = now
    deal.last_interaction_at = now
    if target_stage.is_closed_won or target_stage.is_closed_lost:
        deal.closed_at = now
        # Auto-cancel pending follow-up tasks on closed deals to prevent zombie task accumulation
        await session.execute(
            update(Task)
            .where(
                Task.tenant_id == deal.tenant_id,
                Task.deal_id == deal.id,
                Task.status.in_(["pending", "in_progress"]),
            )
            .values(status="cancelled", updated_at=now)
        )
    else:
        deal.closed_at = None

    deal.forecast_category = compute_forecast_category(
        win_probability=deal.win_probability,
        is_closed_won=target_stage.is_closed_won,
        is_closed_lost=target_stage.is_closed_lost,
    )

    # 3. Open new SCD Type 2 stage history entry
    session.add(
        DealStageHistory(
            id=uuid.uuid4(),
            tenant_id=deal.tenant_id,
            deal_id=deal.id,
            from_stage_id=previous_stage_id,
            to_stage_id=target_stage.id,
            amount_at_transition=deal.amount,
            win_probability_at_transition=deal.win_probability,
            expected_close_date_at_transition=deal.expected_close_date,
            changed_by=actor_user_id,
            entered_at=now,
            exited_at=None,
            duration_seconds=None,
        )
    )

    # 4. Resolve hierarchical account roll-up for interaction
    resolved_account_id, _, resolved_contact_id = await resolve_interaction_hierarchy(
        session,
        tenant_id=deal.tenant_id,
        account_id=deal.account_id,
        deal_id=deal.id,
        contact_id=deal.contact_id,
        occurred_at=now,
    )

    history_entry = Interaction(
        id=uuid.uuid4(),
        tenant_id=deal.tenant_id,
        user_id=actor_user_id,
        deal_id=deal.id,
        account_id=resolved_account_id,
        contact_id=resolved_contact_id,
        type="stage_change",
        direction="internal",
        subject=f"Deal moved to '{target_stage.name}'",
        content_body=(
            notes
            or f"Stage updated by {actor_name}. Win probability synced to {int(deal.win_probability * 100)}%."
        ),
        occurred_at=now,
    )
    session.add(history_entry)

    # 5. Record System Audit Log
    await record_entity_audit(
        session,
        tenant_id=deal.tenant_id,
        entity_type="deal",
        entity_id=deal.id,
        action="STAGE_CHANGE",
        actor_user_id=actor_user_id,
        changes={
            "stage_id": {"old": str(previous_stage_id), "new": str(target_stage.id)},
            "stage_name": {"new": target_stage.name},
            "win_probability": {"new": str(deal.win_probability)},
            "loss_reason": {"new": deal.loss_reason},
        },
    )

    # 6. Transactional Outbox Event with exact decimal string + integer cents
    decimal_amount = Decimal(str(deal.amount)).quantize(Decimal("0.01"))
    amount_cents = int((decimal_amount * Decimal("100")).to_integral_value())

    outbox_event = OutboxEvent(
        id=uuid.uuid4(),
        tenant_id=deal.tenant_id,
        aggregate_type="deal",
        aggregate_id=deal.id,
        event_type="DealStageChanged",
        payload={
            "deal_id": str(deal.id),
            "previous_stage_id": str(previous_stage_id),
            "new_stage_id": str(target_stage.id),
            "amount": str(decimal_amount),
            "amount_decimal": str(decimal_amount),
            "amount_cents": amount_cents,
            "currency": deal.currency,
            "is_won": deal.is_won,
            "is_lost": deal.is_lost,
            "updated_by": str(actor_user_id),
        },
        status="pending",
    )
    session.add(outbox_event)

    await session.flush()
    await session.refresh(deal)
    return deal


def build_actor_from_user(user: AuthenticatedUser) -> tuple[uuid.UUID, str]:
    return user.id, user.full_name
