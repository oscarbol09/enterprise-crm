"""
Transactional Outbox Relay Service: Publishes pending domain events with retry tracking.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.entities import OutboxEvent

logger = structlog.get_logger(__name__)

EventPublisher = Callable[[OutboxEvent], Awaitable[None]]


async def _default_log_publisher(event: OutboxEvent) -> None:
    logger.info(
        "Outbox domain event published",
        event_id=str(event.id),
        tenant_id=str(event.tenant_id),
        aggregate_type=event.aggregate_type,
        event_type=event.event_type,
    )


async def process_pending_outbox_events(
    session: AsyncSession,
    publisher: EventPublisher | None = None,
    batch_size: int = 50,
    max_retries: int = 5,
) -> dict[str, int]:
    """
    Processes a bounded batch of pending `outbox_events` rows using `SKIP LOCKED` on PostgreSQL.
    """
    publish_fn = publisher or _default_log_publisher
    bind = session.get_bind()

    stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.status == "pending")
        .order_by(OutboxEvent.created_at.asc())
        .limit(batch_size)
    )
    if bind is not None and bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    events = list((await session.scalars(stmt)).all())
    stats = {"processed": 0, "published": 0, "retried": 0, "failed": 0}

    for event in events:
        stats["processed"] += 1
        try:
            await publish_fn(event)
            event.status = "published"
            event.processed_at = datetime.now(UTC)
            stats["published"] += 1
        except Exception as exc:
            event.retry_count += 1
            logger.warning(
                "Outbox event delivery failed",
                event_id=str(event.id),
                retry_count=event.retry_count,
                error=str(exc),
            )
            if event.retry_count >= max_retries:
                event.status = "failed"
                event.processed_at = datetime.now(UTC)
                stats["failed"] += 1
            else:
                stats["retried"] += 1

    await session.flush()
    return stats
