"""
Pipeline Domain Service: Default Stage Bootstrapping, Forecasting & Stage Transitions.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.entities import Deal, Interaction, OutboxEvent, Pipeline, PipelineStage
from src.schemas.crm import AuthenticatedUser

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
    notes: str | None = None,
) -> Deal:
    """
    Applies a validated stage transition on a Deal, syncing probability, forecast category,
    activity timeline interaction, and transactional outbox event atomically.
    """
    previous_stage_id = deal.stage_id

    deal.stage_id = target_stage.id
    deal.win_probability = target_stage.default_probability
    deal.is_won = target_stage.is_closed_won
    deal.is_lost = target_stage.is_closed_lost
    deal.loss_reason = loss_reason if target_stage.is_closed_lost else None
    deal.forecast_category = compute_forecast_category(
        win_probability=deal.win_probability,
        is_closed_won=target_stage.is_closed_won,
        is_closed_lost=target_stage.is_closed_lost,
    )

    history_entry = Interaction(
        id=uuid.uuid4(),
        tenant_id=deal.tenant_id,
        user_id=actor_user_id,
        deal_id=deal.id,
        account_id=deal.account_id,
        contact_id=deal.contact_id,
        type="stage_change",
        direction="internal",
        subject=f"Deal moved to '{target_stage.name}'",
        content_body=(
            notes
            or f"Stage updated by {actor_name}. Win probability synced to {int(deal.win_probability * 100)}%."
        ),
    )
    session.add(history_entry)

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
            "amount": float(deal.amount),
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
