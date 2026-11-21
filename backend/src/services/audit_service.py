"""
System Audit Trail, Cursor Pagination & Hierarchical Activity Roll-Up Service.
"""

import base64
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.entities import Contact, Deal, EntityAuditLog, Interaction


async def record_entity_audit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    actor_user_id: uuid.UUID | None,
    changes: dict[str, Any],
) -> EntityAuditLog:
    """Writes an immutable system audit log entry separate from the sales activity timeline."""
    entry = EntityAuditLog(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_user_id=actor_user_id,
        changes=changes,
    )
    session.add(entry)
    return entry


async def resolve_interaction_hierarchy(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    account_id: uuid.UUID | None,
    deal_id: uuid.UUID | None,
    contact_id: uuid.UUID | None,
    occurred_at: datetime | None = None,
    direction: str | None = None,
) -> tuple[uuid.UUID | None, uuid.UUID | None, uuid.UUID | None]:
    """
    Propagates `account_id` and `contact_id` up the entity graph at ingestion time
    so account-level timeline roll-ups execute in O(1) index seek time without multi-table UNIONs.
    Also updates `deal.last_interaction_at` and bidirectional inbound/outbound timestamps.
    """
    resolved_account_id = account_id
    resolved_contact_id = contact_id
    event_time = occurred_at or datetime.now(UTC)

    if deal_id:
        deal = await session.scalar(
            select(Deal).where(Deal.id == deal_id, Deal.tenant_id == tenant_id)
        )
        if deal:
            if resolved_account_id is None and deal.account_id is not None:
                resolved_account_id = deal.account_id
            if resolved_contact_id is None and deal.contact_id is not None:
                resolved_contact_id = deal.contact_id
            deal.last_interaction_at = event_time
            if direction == "inbound":
                deal.last_inbound_activity_at = event_time
            elif direction == "outbound":
                deal.last_outbound_activity_at = event_time

    if resolved_account_id is None and resolved_contact_id is not None:
        contact_acc = await session.scalar(
            select(Contact.account_id).where(
                Contact.id == resolved_contact_id,
                Contact.tenant_id == tenant_id,
            )
        )
        if contact_acc is not None:
            resolved_account_id = contact_acc

    return resolved_account_id, deal_id, resolved_contact_id


def encode_timeline_cursor(occurred_at: datetime, interaction_id: uuid.UUID) -> str:
    payload = {
        "ts": occurred_at.isoformat(),
        "id": str(interaction_id),
    }
    raw = json.dumps(payload).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_timeline_cursor(cursor: str) -> tuple[datetime, uuid.UUID] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        data = json.loads(raw)
        ts = datetime.fromisoformat(data["ts"])
        item_id = uuid.UUID(data["id"])
        return ts, item_id
    except Exception:
        return None


def paginate_interactions_with_cursor(
    interactions: list[Interaction],
    cursor: str | None,
    limit: int,
) -> tuple[list[Interaction], str | None]:
    """
    Applies deterministic keyset filtering `(occurred_at, id)` sorted descending
    and produces the `next_cursor` token when more items exist.
    """
    # Ensure deterministic descending sort by (occurred_at, id)
    sorted_items = sorted(
        interactions,
        key=lambda x: (
            x.occurred_at.replace(tzinfo=UTC) if x.occurred_at.tzinfo is None else x.occurred_at,
            str(x.id),
        ),
        reverse=True,
    )

    if cursor:
        decoded = decode_timeline_cursor(cursor)
        if decoded:
            cursor_ts, cursor_id = decoded
            cursor_ts_aware = cursor_ts.replace(tzinfo=UTC) if cursor_ts.tzinfo is None else cursor_ts
            filtered: list[Interaction] = []
            for item in sorted_items:
                item_ts = (
                    item.occurred_at.replace(tzinfo=UTC)
                    if item.occurred_at.tzinfo is None
                    else item.occurred_at
                )
                if (item_ts, str(item.id)) < (cursor_ts_aware, str(cursor_id)):
                    filtered.append(item)
            sorted_items = filtered

    page = sorted_items[:limit]
    next_cursor: str | None = None
    if len(sorted_items) > limit and page:
        last = page[-1]
        next_cursor = encode_timeline_cursor(last.occurred_at, last.id)

    return page, next_cursor


def apply_sql_keyset_cursor(stmt: Any, model: Any, cursor: str | None) -> Any:
    """
    Applies a composite keyset predicate `(created_at DESC, id DESC)` directly in SQL
    to avoid O(N) OFFSET scans on large CRM master tables.
    """
    if not cursor:
        return stmt
    decoded = decode_timeline_cursor(cursor)
    if not decoded:
        return stmt
    cursor_ts, cursor_id = decoded
    return stmt.where(
        or_(
            model.created_at < cursor_ts,
            and_(model.created_at == cursor_ts, model.id < cursor_id),
        )
    )


def slice_keyset_page(items: list[Any], limit: int) -> tuple[list[Any], str | None]:
    """Slices a `limit + 1` result list into the current page and an optional next cursor."""
    has_more = len(items) > limit
    page = items[:limit]
    next_cursor: str | None = None
    if has_more and page:
        last = page[-1]
        next_cursor = encode_timeline_cursor(last.created_at, last.id)
    return page, next_cursor
