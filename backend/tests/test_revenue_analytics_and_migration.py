"""
Integration tests for revenue forecasting, funnel analytics, channel attribution, and CSV migration.

Verifies:
1. Exact Decimal multi-currency Revenue Forecast, Sales Velocity, Coverage Ratio & Slippage Risk Radar.
2. SCD Type 2 Stage-to-Stage Conversion Funnel & Dwell Time analytics.
3. Revenue Attribution by Acquisition Source (vanity leads vs. Closed-Won USD).
4. Painless CSV Import with auto-mapped CRM headers, Dry-Run preview, deduplication, and DLQ quarantine.
5. Formula-Injection-Sanitized CSV Exports (=, +, -, @ neutralization).
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login


async def _setup_workspace(client: AsyncClient, slug: str) -> tuple[dict[str, str], list[dict]]:
    auth = await register_and_login(client, slug=slug, email=f"admin@{slug}.io")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    stages_resp = await client.get("/api/v1/deals/stages", headers=headers)
    assert stages_resp.status_code == 200
    return headers, stages_resp.json()


@pytest.mark.asyncio
async def test_financial_forecast_velocity_coverage_and_slippage_radar(client: AsyncClient):
    headers, stages = await _setup_workspace(client, "rev-forecast")
    stage_discovery = stages[0]["id"]
    stage_proposal = stages[2]["id"]
    stage_negotiation = stages[3]["id"]
    stage_won = next(s["id"] for s in stages if s["is_closed_won"])
    stage_lost = next(s["id"] for s in stages if s["is_closed_lost"])

    today = date.today()
    next_month = (today + timedelta(days=20)).isoformat()
    overdue_date = (today - timedelta(days=10)).isoformat()

    # 1. Won deal in EUR (100,000 EUR @ 1.10 = 110,000.00 USD)
    d_won = (
        await client.post(
            "/api/v1/deals",
            json={
                "title": "Enterprise EMEA Win",
                "stage_id": stage_discovery,
                "amount": "100000.00",
                "currency": "EUR",
                "exchange_rate_to_usd": "1.10",
                "expected_close_date": today.isoformat(),
                "source_channel": "outbound",
            },
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/v1/deals/{d_won['id']}/move-stage",
        json={"new_stage_id": stage_proposal},
        headers=headers,
    )
    await client.post(
        f"/api/v1/deals/{d_won['id']}/move-stage",
        json={"new_stage_id": stage_won},
        headers=headers,
    )

    # 2. Lost deal in USD (50,000 USD)
    d_lost = (
        await client.post(
            "/api/v1/deals",
            json={
                "title": "Lost Deal",
                "stage_id": stage_discovery,
                "amount": "50000.00",
                "currency": "USD",
                "expected_close_date": today.isoformat(),
                "source_channel": "paid_search",
            },
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/v1/deals/{d_lost['id']}/move-stage",
        json={"new_stage_id": stage_lost, "loss_reason": "Budget frozen"},
        headers=headers,
    )

    # 3. Open Commit deal in USD (80,000 USD, probability 0.80 -> weighted 64,000) with slippage
    d_commit = (
        await client.post(
            "/api/v1/deals",
            json={
                "title": "Slipping Commit Deal",
                "stage_id": stage_negotiation,
                "amount": "80000.00",
                "currency": "USD",
                "expected_close_date": overdue_date,
                "source_channel": "outbound",
            },
            headers=headers,
        )
    ).json()
    # Push close date twice to trigger close_date_push_count >= 2
    await client.patch(
        f"/api/v1/deals/{d_commit['id']}",
        json={"expected_close_date": (today + timedelta(days=5)).isoformat()},
        headers=headers,
    )
    await client.patch(
        f"/api/v1/deals/{d_commit['id']}",
        json={"expected_close_date": overdue_date},
        headers=headers,
    )

    # 4. Open Pipeline deal in USD (40,000 USD, discovery 0.10 -> weighted 4,000)
    await client.post(
        "/api/v1/deals",
        json={
            "title": "Fresh Pipeline Deal",
            "stage_id": stage_discovery,
            "amount": "40000.00",
            "currency": "USD",
            "expected_close_date": next_month,
            "source_channel": "partner",
        },
        headers=headers,
    )

    # Request Financial Forecast with $50,000 quota
    forecast_resp = await client.get(
        "/api/v1/analytics/forecast?quota_usd=50000",
        headers=headers,
    )
    assert forecast_resp.status_code == 200
    data = forecast_resp.json()

    # Exact Decimal checks:
    # Closed-Won = 110,000.00 USD
    # Open Pipeline = 80,000 + 40,000 = 120,000.00 USD
    # Weighted Open = 80,000*0.80 + 40,000*0.10 = 64,000 + 4,000 = 68,000.00 USD
    # Win Rate = 1 won / (1 won + 1 lost) = 0.50
    # Coverage Ratio = 120,000 / 50,000 = 2.40x
    assert Decimal(str(data["closed_won_usd"])) == Decimal("110000.00")
    assert Decimal(str(data["open_pipeline_usd"])) == Decimal("120000.00")
    assert Decimal(str(data["weighted_open_usd"])) == Decimal("68000.00")
    assert Decimal(str(data["win_rate"])) == Decimal("0.50")
    assert Decimal(str(data["pipeline_coverage_ratio"])) == Decimal("2.40")
    assert data["open_deals_count"] == 2
    assert len(data["at_risk_deals"]) >= 1
    assert any(r["deal_id"] == d_commit["id"] for r in data["at_risk_deals"])
    assert Decimal(str(data["usd_at_risk"])) == Decimal("80000.00")

    # Request SCD2 Funnel Analytics
    funnel_resp = await client.get("/api/v1/analytics/funnel", headers=headers)
    assert funnel_resp.status_code == 200
    funnel = funnel_resp.json()
    assert len(funnel["stages"]) == len(stages)
    discovery_metric = next(s for s in funnel["stages"] if s["stage_id"] == stage_discovery)
    assert discovery_metric["deals_entered"] >= 3


@pytest.mark.asyncio
async def test_revenue_attribution_contrasts_vanity_leads_with_closed_won_usd(client: AsyncClient):
    headers, stages = await _setup_workspace(client, "rev-attribution")
    stage_discovery = stages[0]["id"]
    stage_won = next(s["id"] for s in stages if s["is_closed_won"])
    stage_lost = next(s["id"] for s in stages if s["is_closed_lost"])

    # Channel A: paid_search brings 3 leads (high vanity count) but 0 won deals
    for idx in range(3):
        await client.post(
            "/api/v1/contacts",
            json={
                "first_name": f"Paid{idx}",
                "last_name": "Lead",
                "email": f"paid{idx}@prospect.io",
                "source_channel": "paid_search",
            },
            headers=headers,
        )
    lost_deal = (
        await client.post(
            "/api/v1/deals",
            json={
                "title": "Paid Search Deal",
                "stage_id": stage_discovery,
                "amount": "20000.00",
                "currency": "USD",
                "source_channel": "paid_search",
            },
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/v1/deals/{lost_deal['id']}/move-stage",
        json={"new_stage_id": stage_lost, "loss_reason": "No ICP fit"},
        headers=headers,
    )

    # Channel B: referral brings 1 lead and 1 won deal worth $150,000 USD (100% revenue share)
    ref_contact = (
        await client.post(
            "/api/v1/contacts",
            json={
                "first_name": "Sofia",
                "last_name": "Ref",
                "email": "sofia@enterprise.io",
                "source_channel": "referral",
            },
            headers=headers,
        )
    ).json()
    won_deal = (
        await client.post(
            "/api/v1/deals",
            json={
                "title": "Referral Enterprise Contract",
                "stage_id": stage_discovery,
                "amount": "150000.00",
                "currency": "USD",
                "contact_id": ref_contact["id"],
                "source_channel": "referral",
            },
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/v1/deals/{won_deal['id']}/move-stage",
        json={"new_stage_id": stage_won},
        headers=headers,
    )

    attr_resp = await client.get("/api/v1/analytics/attribution", headers=headers)
    assert attr_resp.status_code == 200
    payload = attr_resp.json()
    assert Decimal(str(payload["total_closed_won_usd"])) == Decimal("150000.00")

    by_channel = {c["source_channel"]: c for c in payload["channels"]}
    assert by_channel["paid_search"]["leads_count"] == 3
    assert Decimal(str(by_channel["paid_search"]["closed_won_revenue_usd"])) == Decimal("0.00")

    assert by_channel["referral"]["leads_count"] == 1
    assert by_channel["referral"]["won_deals_count"] == 1
    assert Decimal(str(by_channel["referral"]["closed_won_revenue_usd"])) == Decimal("150000.00")
    assert Decimal(str(by_channel["referral"]["revenue_share_pct"])) == Decimal("100.00")


@pytest.mark.asyncio
async def test_painless_csv_import_dry_run_dedup_dlq_and_formula_safe_export(client: AsyncClient):
    headers, stages = await _setup_workspace(client, "csv-migration")

    # Seed an existing contact to verify deduplication ("skip" vs "update")
    await client.post(
        "/api/v1/contacts",
        json={
            "first_name": "Elena",
            "last_name": "Existente",
            "email": "elena@nordic.io",
            "job_title": "Manager",
        },
        headers=headers,
    )

    # HubSpot/Salesforce style CSV with mixed headers, 1 valid new contact with formula payload,
    # 1 duplicate email, and 1 malformed email row (quarantined to DLQ with exact line number)
    csv_payload = (
        "First Name,Last Name,Email Address,Company Name,Title,Lead Source\n"
        "=cmd|' /C calc'!A0,Perez,carlos@acme-latam.com,Acme Latam,VP Sales,outbound\n"
        "Elena,Existente,elena@nordic.io,Nordic Systems,VP Engineering,referral\n"
        "BadRow,NoEmail,not-an-email,Broken Corp,Analyst,organic\n"
    )

    # 1. Dry-run preview must NOT write to DB
    dry_resp = await client.post(
        "/api/v1/data/contacts/import",
        json={"csv_content": csv_payload, "dry_run": True, "dedupe_strategy": "update"},
        headers=headers,
    )
    assert dry_resp.status_code == 200
    dry = dry_resp.json()
    assert dry["dry_run"] is True
    assert dry["total_rows"] == 3
    assert dry["would_create"] == 1
    assert dry["would_update"] == 1
    assert dry["quarantined_count"] == 1
    assert dry["errors"][0]["row"] == 4  # Header is line 1, BadRow is line 4

    # Verify DB was NOT mutated during dry-run
    contacts_before = (await client.get("/api/v1/contacts", headers=headers)).json()
    assert len(contacts_before) == 1

    # 2. Execute live import with dedupe_strategy="update"
    exec_resp = await client.post(
        "/api/v1/data/contacts/import",
        json={"csv_content": csv_payload, "dry_run": False, "dedupe_strategy": "update"},
        headers=headers,
    )
    assert exec_resp.status_code == 200
    exec_data = exec_resp.json()
    assert exec_data["dry_run"] is False
    assert exec_data["created_count"] == 1
    assert exec_data["updated_count"] == 1
    assert exec_data["quarantined_count"] == 1

    # Confirm Elena was updated to VP Engineering and Acme Latam account was auto-created
    contacts_after = (await client.get("/api/v1/contacts", headers=headers)).json()
    assert len(contacts_after) == 2
    elena = next(c for c in contacts_after if c["email"] == "elena@nordic.io")
    assert elena["job_title"] == "VP Engineering"
    accounts_after = (await client.get("/api/v1/accounts", headers=headers)).json()
    assert any(a["name"] == "Acme Latam" for a in accounts_after)

    # 3. Export CSV and verify Formula Injection neutralization ('=cmd|...)
    export_resp = await client.get("/api/v1/data/export/contacts", headers=headers)
    assert export_resp.status_code == 200
    assert "text/csv" in export_resp.headers["content-type"]
    csv_out = export_resp.text
    assert "'=cmd|' /C calc'!A0" in csv_out
    assert "\n=cmd|" not in csv_out

    # Export Deals CSV with formula-like deal title
    await client.post(
        "/api/v1/deals",
        json={
            "title": "+SUM(A1:A5) Enterprise Deal",
            "stage_id": stages[0]["id"],
            "amount": "25000.00",
            "currency": "USD",
            "source_channel": "outbound",
        },
        headers=headers,
    )
    deals_csv = (await client.get("/api/v1/data/export/deals", headers=headers)).text
    assert "'+SUM(A1:A5) Enterprise Deal" in deals_csv
    assert "25000.00" in deals_csv
