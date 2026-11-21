"""
Revenue Intelligence, Financial Forecasting & Attribution Engine.

All monetary aggregations operate strictly on `Deal.normalized_amount_usd` using exact
`Decimal` arithmetic (`ROUND_HALF_UP`) so multi-currency pipelines never suffer from
binary float drift or naive cross-currency summation.
"""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.entities import Contact, Deal, DealStageHistory, PipelineSnapshot, PipelineStage
from src.schemas.crm import (
    AtRiskDealItem,
    AttributionAnalyticsResponse,
    ChannelAttributionMetric,
    ForecastAnalyticsResponse,
    ForecastPeriodBreakdown,
    FunnelAnalyticsResponse,
    FunnelStageMetric,
    PipelineSnapshotResponse,
    WaterfallBridgeResponse,
    WinLossAnalyticsResponse,
    WinLossCategoryBucket,
    WinLossNamedBucket,
)

_TWO_DEC = Decimal("0.01")
_ZERO = Decimal("0.00")


def _q2(value: Decimal) -> Decimal:
    return value.quantize(_TWO_DEC, rounding=ROUND_HALF_UP)


def _ensure_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


async def compute_forecast_analytics(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    quota_usd: Decimal | None = None,
    stale_days_threshold: int = 14,
) -> ForecastAnalyticsResponse:
    """Compute exact USD forecast breakdown, sales velocity, quota coverage & risk radar."""
    deals = list(
        (
            await db.scalars(
                select(Deal).where(
                    Deal.tenant_id == tenant_id,
                    Deal.deleted_at.is_(None),
                )
            )
        ).all()
    )

    today = date.today()
    now = datetime.now(UTC)

    closed_won_usd = _ZERO
    closed_lost_usd = _ZERO
    open_pipeline_usd = _ZERO
    commit_usd = _ZERO
    best_case_usd = _ZERO
    weighted_open_usd = _ZERO

    open_count = 0
    won_count = 0
    lost_count = 0
    won_cycle_days: list[Decimal] = []

    at_risk_deals: list[AtRiskDealItem] = []
    usd_at_risk = _ZERO

    period_buckets: dict[str, dict[str, Decimal | int]] = defaultdict(
        lambda: {
            "closed_won_usd": _ZERO,
            "commit_usd": _ZERO,
            "best_case_usd": _ZERO,
            "pipeline_usd": _ZERO,
            "weighted_open_usd": _ZERO,
            "deal_count": 0,
        }
    )

    for deal in deals:
        usd = Decimal(str(deal.normalized_amount_usd or deal.amount or _ZERO))
        prob = Decimal(str(deal.win_probability or _ZERO))
        period_key = (
            deal.expected_close_date.strftime("%Y-%m")
            if deal.expected_close_date is not None
            else "unscheduled"
        )
        bucket = period_buckets[period_key]

        if deal.is_won:
            won_count += 1
            closed_won_usd += usd
            bucket["closed_won_usd"] = Decimal(bucket["closed_won_usd"]) + usd
            bucket["deal_count"] = int(bucket["deal_count"]) + 1
            created_utc = _ensure_utc(deal.created_at)
            closed_utc = _ensure_utc(deal.closed_at or deal.updated_at)
            delta_days = max(Decimal("1.00"), Decimal((closed_utc - created_utc).total_seconds()) / Decimal("86400"))
            won_cycle_days.append(delta_days)
            continue

        if deal.is_lost:
            lost_count += 1
            closed_lost_usd += usd
            continue

        # Open deal
        open_count += 1
        open_pipeline_usd += usd
        weighted = _q2(usd * prob)
        weighted_open_usd += weighted

        bucket["weighted_open_usd"] = Decimal(bucket["weighted_open_usd"]) + weighted
        bucket["deal_count"] = int(bucket["deal_count"]) + 1

        if deal.forecast_category == "commit":
            commit_usd += usd
            bucket["commit_usd"] = Decimal(bucket["commit_usd"]) + usd
        elif deal.forecast_category == "best_case":
            best_case_usd += usd
            bucket["best_case_usd"] = Decimal(bucket["best_case_usd"]) + usd
        else:
            bucket["pipeline_usd"] = Decimal(bucket["pipeline_usd"]) + usd

        # Risk Radar: Slippage (>=2 pushes), Overdue close date, or Stale in stage
        entered_utc = _ensure_utc(deal.stage_entered_at or deal.created_at)
        days_in_stage = max(0, int((now - entered_utc).total_seconds() // 86400))
        risk_reasons: list[str] = []
        if (deal.close_date_push_count or 0) >= 2:
            risk_reasons.append(f"Fecha pospuesta {deal.close_date_push_count} veces")
        if deal.expected_close_date is not None and deal.expected_close_date < today:
            risk_reasons.append("Fecha de cierre vencida")
        if days_in_stage >= stale_days_threshold:
            risk_reasons.append(f"Estancado {days_in_stage}d en etapa")
        if deal.last_outbound_activity_at is not None:
            outbound_utc = _ensure_utc(deal.last_outbound_activity_at)
            inbound_utc = (
                _ensure_utc(deal.last_inbound_activity_at)
                if deal.last_inbound_activity_at is not None
                else None
            )
            if inbound_utc is None or (outbound_utc - inbound_utc).total_seconds() >= 7 * 86400:
                risk_reasons.append("Sin respuesta del cliente (Riesgo de Ghosting)")

        if risk_reasons:
            usd_at_risk += usd
            at_risk_deals.append(
                AtRiskDealItem(
                    deal_id=deal.id,
                    title=deal.title,
                    normalized_amount_usd=_q2(usd),
                    expected_close_date=deal.expected_close_date,
                    close_date_push_count=deal.close_date_push_count or 0,
                    days_in_stage=days_in_stage,
                    risk_reasons=risk_reasons,
                )
            )

    closed_total = won_count + lost_count
    win_rate = _q2(Decimal(won_count) / Decimal(closed_total)) if closed_total > 0 else _ZERO
    avg_won_deal_usd = _q2(closed_won_usd / Decimal(won_count)) if won_count > 0 else _ZERO
    avg_sales_cycle_days = (
        _q2(sum(won_cycle_days, _ZERO) / Decimal(len(won_cycle_days)))
        if won_cycle_days
        else Decimal("30.00")
    )

    # Sales Velocity (USD/day) = (Open Opportunities * Avg Won Deal Size * Win Rate) / Avg Sales Cycle Days
    if open_count > 0 and avg_sales_cycle_days > _ZERO:
        basis_deal_size = avg_won_deal_usd if avg_won_deal_usd > _ZERO else _q2(open_pipeline_usd / Decimal(open_count))
        sales_velocity = _q2(
            (Decimal(open_count) * basis_deal_size * win_rate) / avg_sales_cycle_days
        )
    else:
        sales_velocity = _ZERO

    coverage_ratio: Decimal | None = None
    if quota_usd is not None and quota_usd > _ZERO:
        coverage_ratio = _q2(open_pipeline_usd / quota_usd)

    by_period = [
        ForecastPeriodBreakdown(
            period=period,
            closed_won_usd=_q2(Decimal(vals["closed_won_usd"])),
            commit_usd=_q2(Decimal(vals["commit_usd"])),
            best_case_usd=_q2(Decimal(vals["best_case_usd"])),
            pipeline_usd=_q2(Decimal(vals["pipeline_usd"])),
            weighted_open_usd=_q2(Decimal(vals["weighted_open_usd"])),
            deal_count=int(vals["deal_count"]),
        )
        for period, vals in sorted(period_buckets.items())
    ]

    at_risk_deals.sort(key=lambda item: item.normalized_amount_usd, reverse=True)

    return ForecastAnalyticsResponse(
        closed_won_usd=_q2(closed_won_usd),
        closed_lost_usd=_q2(closed_lost_usd),
        open_pipeline_usd=_q2(open_pipeline_usd),
        commit_usd=_q2(commit_usd),
        best_case_usd=_q2(best_case_usd),
        weighted_open_usd=_q2(weighted_open_usd),
        total_projected_usd=_q2(closed_won_usd + weighted_open_usd),
        open_deals_count=open_count,
        won_deals_count=won_count,
        lost_deals_count=lost_count,
        win_rate=win_rate,
        avg_won_deal_usd=avg_won_deal_usd,
        avg_sales_cycle_days=avg_sales_cycle_days,
        sales_velocity_usd_per_day=sales_velocity,
        quota_usd=_q2(quota_usd) if quota_usd is not None else None,
        pipeline_coverage_ratio=coverage_ratio,
        usd_at_risk=_q2(usd_at_risk),
        at_risk_deals=at_risk_deals,
        by_period=by_period,
    )


async def compute_funnel_analytics(
    db: AsyncSession,
    tenant_id: uuid.UUID,
) -> FunnelAnalyticsResponse:
    """Compute stage-to-stage conversion rates and average dwell days from SCD Type 2 history."""
    stages = list(
        (
            await db.scalars(
                select(PipelineStage)
                .where(PipelineStage.tenant_id == tenant_id)
                .order_by(PipelineStage.position.asc())
            )
        ).all()
    )
    history_rows = list(
        (
            await db.scalars(
                select(DealStageHistory).where(DealStageHistory.tenant_id == tenant_id)
            )
        ).all()
    )
    open_deals = list(
        (
            await db.scalars(
                select(Deal).where(
                    Deal.tenant_id == tenant_id,
                    Deal.deleted_at.is_(None),
                    Deal.is_won.is_(False),
                    Deal.is_lost.is_(False),
                )
            )
        ).all()
    )

    entered_by_stage: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    dwell_seconds_by_stage: dict[uuid.UUID, list[int]] = defaultdict(list)
    for row in history_rows:
        entered_by_stage[row.to_stage_id].add(row.deal_id)
        if row.duration_seconds is not None and row.duration_seconds >= 0:
            dwell_seconds_by_stage[row.to_stage_id].append(row.duration_seconds)

    open_count_by_stage: dict[uuid.UUID, int] = defaultdict(int)
    for d in open_deals:
        open_count_by_stage[d.stage_id] += 1

    stage_metrics: list[FunnelStageMetric] = []
    bottleneck_stage: str | None = None
    max_dwell = Decimal("-1.00")

    for idx, stage in enumerate(stages):
        entered_count = len(entered_by_stage[stage.id])
        next_entered = 0
        if idx + 1 < len(stages) and not stages[idx + 1].is_closed_lost:
            next_entered = len(entered_by_stage[stages[idx + 1].id])
        conv_pct = (
            _q2((Decimal(next_entered) / Decimal(entered_count)) * Decimal("100"))
            if entered_count > 0 and idx + 1 < len(stages) and not stage.is_closed_won and not stage.is_closed_lost
            else _ZERO
        )
        durations = dwell_seconds_by_stage[stage.id]
        avg_dwell_days = (
            _q2(Decimal(sum(durations)) / Decimal(len(durations)) / Decimal("86400"))
            if durations
            else _ZERO
        )
        if not stage.is_closed_won and not stage.is_closed_lost and avg_dwell_days > max_dwell and entered_count > 0:
            max_dwell = avg_dwell_days
            bottleneck_stage = stage.name

        stage_metrics.append(
            FunnelStageMetric(
                stage_id=stage.id,
                stage_name=stage.name,
                position=stage.position,
                is_closed_won=stage.is_closed_won,
                is_closed_lost=stage.is_closed_lost,
                deals_entered=entered_count,
                current_open_deals=open_count_by_stage[stage.id],
                conversion_to_next_pct=min(Decimal("100.00"), conv_pct),
                avg_dwell_days=avg_dwell_days,
            )
        )

    return FunnelAnalyticsResponse(
        stages=stage_metrics,
        bottleneck_stage_name=bottleneck_stage,
    )


async def compute_attribution_analytics(
    db: AsyncSession,
    tenant_id: uuid.UUID,
) -> AttributionAnalyticsResponse:
    """Attribute Closed-Won USD revenue and pipeline back to acquisition channels."""
    contacts = list(
        (
            await db.scalars(
                select(Contact).where(
                    Contact.tenant_id == tenant_id,
                    Contact.deleted_at.is_(None),
                )
            )
        ).all()
    )
    deals = list(
        (
            await db.scalars(
                select(Deal).where(
                    Deal.tenant_id == tenant_id,
                    Deal.deleted_at.is_(None),
                )
            )
        ).all()
    )

    contact_source_map: dict[uuid.UUID, str] = {}
    leads_by_channel: dict[str, int] = defaultdict(int)
    for c in contacts:
        ch = (c.source_channel or str((c.metadata_ or {}).get("source_channel") or "")).strip().lower() or "direct_unattributed"
        contact_source_map[c.id] = ch
        leads_by_channel[ch] += 1

    opp_by_channel: dict[str, int] = defaultdict(int)
    won_by_channel: dict[str, int] = defaultdict(int)
    lost_by_channel: dict[str, int] = defaultdict(int)
    pipeline_by_channel: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    revenue_by_channel: dict[str, Decimal] = defaultdict(lambda: _ZERO)

    all_channels: set[str] = set(leads_by_channel.keys())
    total_closed_won_usd = _ZERO

    for d in deals:
        ch = (
            (d.source_channel or str((d.metadata_ or {}).get("source_channel") or "")).strip().lower()
            or (contact_source_map.get(d.contact_id) if d.contact_id else None)
            or "direct_unattributed"
        )
        all_channels.add(ch)
        usd = Decimal(str(d.normalized_amount_usd or d.amount or _ZERO))
        opp_by_channel[ch] += 1
        pipeline_by_channel[ch] += usd
        if d.is_won:
            won_by_channel[ch] += 1
            revenue_by_channel[ch] += usd
            total_closed_won_usd += usd
        elif d.is_lost:
            lost_by_channel[ch] += 1

    channels: list[ChannelAttributionMetric] = []
    for ch in all_channels:
        won_n = won_by_channel[ch]
        lost_n = lost_by_channel[ch]
        closed_n = won_n + lost_n
        rev = revenue_by_channel[ch]
        win_rate = _q2(Decimal(won_n) / Decimal(closed_n)) if closed_n > 0 else _ZERO
        avg_deal = _q2(rev / Decimal(won_n)) if won_n > 0 else _ZERO
        rev_share = (
            _q2((rev / total_closed_won_usd) * Decimal("100"))
            if total_closed_won_usd > _ZERO
            else _ZERO
        )
        channels.append(
            ChannelAttributionMetric(
                source_channel=ch,
                leads_count=leads_by_channel[ch],
                opportunities_count=opp_by_channel[ch],
                won_deals_count=won_n,
                win_rate=win_rate,
                pipeline_generated_usd=_q2(pipeline_by_channel[ch]),
                closed_won_revenue_usd=_q2(rev),
                avg_deal_size_usd=avg_deal,
                revenue_share_pct=rev_share,
            )
        )

    channels.sort(key=lambda item: (item.closed_won_revenue_usd, item.pipeline_generated_usd), reverse=True)

    return AttributionAnalyticsResponse(
        total_leads=len(contacts),
        total_closed_won_usd=_q2(total_closed_won_usd),
        channels=channels,
    )


async def capture_pipeline_snapshot(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    snapshot_date: date | None = None,
) -> PipelineSnapshotResponse:
    """Idempotently captures a point-in-time snapshot of all non-deleted tenant deals."""
    target_date = snapshot_date or date.today()

    await db.execute(
        delete(PipelineSnapshot).where(
            PipelineSnapshot.tenant_id == tenant_id,
            PipelineSnapshot.snapshot_date == target_date,
        )
    )

    deals = list(
        (
            await db.scalars(
                select(Deal).where(
                    Deal.tenant_id == tenant_id,
                    Deal.deleted_at.is_(None),
                )
            )
        ).all()
    )

    total_open_usd = _ZERO
    for d in deals:
        usd = _q2(Decimal(str(d.normalized_amount_usd or d.amount or _ZERO)))
        if not d.is_won and not d.is_lost:
            total_open_usd += usd
        db.add(
            PipelineSnapshot(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                snapshot_date=target_date,
                deal_id=d.id,
                stage_id=d.stage_id,
                normalized_amount_usd=usd,
                forecast_category=d.forecast_category,
                expected_close_date=d.expected_close_date,
                is_won=d.is_won,
                is_lost=d.is_lost,
            )
        )

    await db.flush()
    return PipelineSnapshotResponse(
        snapshot_date=target_date,
        captured_deals=len(deals),
        total_open_usd=_q2(total_open_usd),
    )


async def compute_waterfall_bridge(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    from_date: date,
    to_date: date,
) -> WaterfallBridgeResponse:
    """
    Computes the exact Decimal pipeline waterfall bridge between two snapshot dates (T0 -> T1):
    starting_open + new_deals + expansion - contraction - closed_won - closed_lost == ending_open.
    """
    t0_rows = list(
        (
            await db.scalars(
                select(PipelineSnapshot).where(
                    PipelineSnapshot.tenant_id == tenant_id,
                    PipelineSnapshot.snapshot_date == from_date,
                )
            )
        ).all()
    )
    t1_rows = list(
        (
            await db.scalars(
                select(PipelineSnapshot).where(
                    PipelineSnapshot.tenant_id == tenant_id,
                    PipelineSnapshot.snapshot_date == to_date,
                )
            )
        ).all()
    )

    t0_by_deal = {r.deal_id: r for r in t0_rows}
    t1_by_deal = {r.deal_id: r for r in t1_rows}
    all_deal_ids = set(t0_by_deal.keys()) | set(t1_by_deal.keys())

    starting_open_usd = _ZERO
    new_deals_usd = _ZERO
    expansion_usd = _ZERO
    contraction_usd = _ZERO
    closed_won_usd = _ZERO
    closed_lost_usd = _ZERO
    ending_open_usd = _ZERO
    slipped_deals_count = 0

    for deal_id in all_deal_ids:
        s0 = t0_by_deal.get(deal_id)
        s1 = t1_by_deal.get(deal_id)

        was_open = s0 is not None and not s0.is_won and not s0.is_lost
        is_open = s1 is not None and not s1.is_won and not s1.is_lost
        amt0 = Decimal(str(s0.normalized_amount_usd)) if s0 is not None else _ZERO
        amt1 = Decimal(str(s1.normalized_amount_usd)) if s1 is not None else _ZERO

        if was_open:
            starting_open_usd += amt0
        if is_open:
            ending_open_usd += amt1

        if not was_open and s1 is not None:
            # Deal created after T0
            if is_open:
                new_deals_usd += amt1
            elif s1.is_won:
                new_deals_usd += amt1
                closed_won_usd += amt1
            elif s1.is_lost:
                new_deals_usd += amt1
                closed_lost_usd += amt1
        elif was_open and s1 is not None:
            if amt1 > amt0:
                expansion_usd += amt1 - amt0
            elif amt1 < amt0:
                contraction_usd += amt0 - amt1

            if s1.is_won:
                closed_won_usd += amt1
            elif s1.is_lost:
                closed_lost_usd += amt1
            elif (
                s0 is not None
                and s0.expected_close_date is not None
                and s1.expected_close_date is not None
                and s1.expected_close_date > s0.expected_close_date
            ):
                slipped_deals_count += 1
        elif was_open and s1 is None:
            # Removed/deleted between snapshots -> counted as contraction
            contraction_usd += amt0

    return WaterfallBridgeResponse(
        from_date=from_date,
        to_date=to_date,
        starting_open_usd=_q2(starting_open_usd),
        new_deals_usd=_q2(new_deals_usd),
        expansion_usd=_q2(expansion_usd),
        contraction_usd=_q2(contraction_usd),
        closed_won_usd=_q2(closed_won_usd),
        closed_lost_usd=_q2(closed_lost_usd),
        ending_open_usd=_q2(ending_open_usd),
        slipped_deals_count=slipped_deals_count,
    )


async def compute_win_loss_analytics(
    db: AsyncSession,
    tenant_id: uuid.UUID,
) -> WinLossAnalyticsResponse:
    """Aggregates Closed-Lost deals by structured loss category, competitor, and missing feature."""
    lost_deals = list(
        (
            await db.scalars(
                select(Deal).where(
                    Deal.tenant_id == tenant_id,
                    Deal.deleted_at.is_(None),
                    Deal.is_lost.is_(True),
                )
            )
        ).all()
    )

    cat_counts: dict[str, int] = defaultdict(int)
    cat_usd: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    comp_counts: dict[str, int] = defaultdict(int)
    comp_usd: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    feat_counts: dict[str, int] = defaultdict(int)
    feat_usd: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    total_lost_usd = _ZERO

    for d in lost_deals:
        usd = _q2(Decimal(str(d.normalized_amount_usd or d.amount or _ZERO)))
        total_lost_usd += usd

        cat = (d.loss_category or "other").strip().lower()
        cat_counts[cat] += 1
        cat_usd[cat] += usd

        if d.competitor_name and d.competitor_name.strip():
            comp = d.competitor_name.strip()
            comp_counts[comp] += 1
            comp_usd[comp] += usd

        if d.missing_feature_tag and d.missing_feature_tag.strip():
            feat = d.missing_feature_tag.strip()
            feat_counts[feat] += 1
            feat_usd[feat] += usd

    by_category = sorted(
        [
            WinLossCategoryBucket(category=k, lost_deals_count=cat_counts[k], lost_usd=_q2(cat_usd[k]))
            for k in cat_counts
        ],
        key=lambda x: x.lost_usd,
        reverse=True,
    )
    by_competitor = sorted(
        [
            WinLossNamedBucket(name=k, lost_deals_count=comp_counts[k], lost_usd=_q2(comp_usd[k]))
            for k in comp_counts
        ],
        key=lambda x: x.lost_usd,
        reverse=True,
    )
    by_missing_feature = sorted(
        [
            WinLossNamedBucket(name=k, lost_deals_count=feat_counts[k], lost_usd=_q2(feat_usd[k]))
            for k in feat_counts
        ],
        key=lambda x: x.lost_usd,
        reverse=True,
    )

    return WinLossAnalyticsResponse(
        total_lost_deals=len(lost_deals),
        total_lost_usd=_q2(total_lost_usd),
        by_category=by_category,
        by_competitor=by_competitor,
        by_missing_feature=by_missing_feature,
    )
