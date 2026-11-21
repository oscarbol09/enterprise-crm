"""
Integration tests for CSV import batch rollback (with bundled deals),
pipeline snapshots waterfall bridge, bidirectional ghosting health,
structured win/loss analytics, and stage-gate header metadata.
"""

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login


async def _bootstrap(client: AsyncClient, slug: str) -> tuple[dict[str, str], list[dict]]:
    auth = await register_and_login(client, slug=slug, email=f"admin@{slug}.io")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    stages = (await client.get("/api/v1/deals/stages", headers=headers)).json()
    return headers, stages


@pytest.mark.asyncio
async def test_csv_bundled_import_and_full_batch_rollback(client: AsyncClient):
    headers, _ = await _bootstrap(client, "batch-rollback")

    csv_payload = (
        "First Name,Last Name,Email Address,Company Name,Title,Lead Source,Deal Name,Deal Amount,Currency\n"
        "Lucia,Mendez,lucia@solaris.io,Solaris Energy,VP Ops,referral,Solaris Annual Plan,45000.00,USD\n"
        "Diego,Vega,diego@solaris.io,Solaris Energy,CTO,referral,Solaris Add-on,15000.00,USD\n"
    )

    resp = await client.post(
        "/api/v1/data/contacts/import",
        json={"csv_content": csv_payload, "dry_run": False, "dedupe_strategy": "skip"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created_count"] == 2
    assert body["accounts_auto_created"] == 1
    assert body["deals_created_count"] == 2
    batch_id = body["import_batch_id"]
    assert batch_id is not None

    assert len((await client.get("/api/v1/contacts", headers=headers)).json()) == 2
    assert len((await client.get("/api/v1/accounts", headers=headers)).json()) == 1
    assert len((await client.get("/api/v1/deals", headers=headers)).json()) == 2

    # Roll back the entire batch in 1 atomic operation
    rb_resp = await client.post(f"/api/v1/data/imports/{batch_id}/rollback", headers=headers)
    assert rb_resp.status_code == 200
    rb = rb_resp.json()
    assert rb["reverted_accounts"] == 1
    assert rb["reverted_contacts"] == 2
    assert rb["reverted_deals"] == 2

    assert len((await client.get("/api/v1/contacts", headers=headers)).json()) == 0
    assert len((await client.get("/api/v1/accounts", headers=headers)).json()) == 0
    assert len((await client.get("/api/v1/deals", headers=headers)).json()) == 0

    # Second rollback must be rejected with 409 Conflict
    rb_again = await client.post(f"/api/v1/data/imports/{batch_id}/rollback", headers=headers)
    assert rb_again.status_code == 409


@pytest.mark.asyncio
async def test_pipeline_snapshots_waterfall_bridge_ghosting_and_win_loss_matrix(client: AsyncClient):
    headers, stages = await _bootstrap(client, "waterfall-ops")
    st_disc = stages[0]["id"]
    st_won = next(s["id"] for s in stages if s["is_closed_won"])
    st_lost = next(s["id"] for s in stages if s["is_closed_lost"])

    t0 = (date.today() - timedelta(days=30)).isoformat()
    t1 = date.today().isoformat()

    # T0: 3 open deals ($50k expand, $40k win, $30k lose) -> starting_open = $120,000.00
    d_expand = (
        await client.post(
            "/api/v1/deals",
            json={"title": "Expansion Deal", "stage_id": st_disc, "amount": "50000.00"},
            headers=headers,
        )
    ).json()
    d_win = (
        await client.post(
            "/api/v1/deals",
            json={"title": "Winning Deal", "stage_id": st_disc, "amount": "40000.00"},
            headers=headers,
        )
    ).json()
    d_lose = (
        await client.post(
            "/api/v1/deals",
            json={"title": "Competitor Loss Deal", "stage_id": st_disc, "amount": "30000.00"},
            headers=headers,
        )
    ).json()

    snap0 = await client.post(
        "/api/v1/analytics/snapshots",
        json={"snapshot_date": t0},
        headers=headers,
    )
    assert snap0.status_code == 201
    assert snap0.json()["captured_deals"] == 3

    # Mutations between T0 and T1:
    # 1. Expand d_expand from 50k -> 70k (+20k expansion)
    await client.patch(
        f"/api/v1/deals/{d_expand['id']}",
        json={"amount": "70000.00"},
        headers=headers,
    )
    # Log outbound activity without inbound reply -> Ghosting Risk
    await client.post(
        "/api/v1/interactions",
        json={
            "deal_id": d_expand["id"],
            "type": "email",
            "direction": "outbound",
            "subject": "Seguimiento sin respuesta",
            "content_body": "Enviado propuesta hace dias.",
        },
        headers=headers,
    )

    # 2. Win d_win ($40k)
    await client.post(
        f"/api/v1/deals/{d_win['id']}/move-stage",
        json={"new_stage_id": st_won},
        headers=headers,
    )

    # 3. Lose d_lose ($30k) with structured competitor & missing feature metadata
    await client.post(
        f"/api/v1/deals/{d_lose['id']}/move-stage",
        json={
            "new_stage_id": st_lost,
            "loss_reason": "Required SAML SSO out of the box",
            "loss_category": "missing_feature",
            "competitor_name": "Salesforce",
            "missing_feature_tag": "SSO/SAML",
        },
        headers=headers,
    )

    # 4. New deal created after T0 ($25k)
    await client.post(
        "/api/v1/deals",
        json={"title": "New Q4 Deal", "stage_id": st_disc, "amount": "25000.00"},
        headers=headers,
    )

    # Capture T1 snapshot
    snap1 = await client.post(
        "/api/v1/analytics/snapshots",
        json={"snapshot_date": t1},
        headers=headers,
    )
    assert snap1.status_code == 201

    # Query Waterfall Bridge (T0 -> T1)
    wf_resp = await client.get(
        f"/api/v1/analytics/waterfall?from_date={t0}&to_date={t1}",
        headers=headers,
    )
    assert wf_resp.status_code == 200
    wf = wf_resp.json()
    # Accounting identity: 120k + 25k (new) + 20k (expansion) - 0 (contraction) - 40k (won) - 30k (lost) = 95k
    assert Decimal(str(wf["starting_open_usd"])) == Decimal("120000.00")
    assert Decimal(str(wf["new_deals_usd"])) == Decimal("25000.00")
    assert Decimal(str(wf["expansion_usd"])) == Decimal("20000.00")
    assert Decimal(str(wf["contraction_usd"])) == Decimal("0.00")
    assert Decimal(str(wf["closed_won_usd"])) == Decimal("40000.00")
    assert Decimal(str(wf["closed_lost_usd"])) == Decimal("30000.00")
    assert Decimal(str(wf["ending_open_usd"])) == Decimal("95000.00")

    # Query Structured Win/Loss Matrix
    wl_resp = await client.get("/api/v1/analytics/win-loss", headers=headers)
    assert wl_resp.status_code == 200
    wl = wl_resp.json()
    assert Decimal(str(wl["total_lost_usd"])) == Decimal("30000.00")
    assert wl["by_category"][0]["category"] == "missing_feature"
    assert wl["by_competitor"][0]["name"] == "Salesforce"
    assert wl["by_missing_feature"][0]["name"] == "SSO/SAML"

    # Verify bidirectional outbound-only Ghosting Risk detection in forecast risk radar
    fc = (await client.get("/api/v1/analytics/forecast", headers=headers)).json()
    expand_risk = next((r for r in fc["at_risk_deals"] if r["deal_id"] == d_expand["id"]), None)
    assert expand_risk is not None
    assert any("Sin respuesta del cliente" in reason for reason in expand_risk["risk_reasons"])


@pytest.mark.asyncio
async def test_stage_gate_violation_emits_structured_missing_fields_header(client: AsyncClient):
    headers, stages = await _bootstrap(client, "stage-gate-ui")
    st_disc = stages[0]["id"]
    st_neg = stages[3]["id"]  # position 4

    # Define a stage-gated required field for stage position >= 4
    cf_resp = await client.post(
        "/api/v1/custom-fields",
        json={
            "entity_type": "deal",
            "field_key": "tax_id_nit",
            "label": "NIT / Tax ID",
            "field_type": "text",
            "is_required": True,
            "min_stage_position": 4,
        },
        headers=headers,
    )
    assert cf_resp.status_code == 201

    deal = (
        await client.post(
            "/api/v1/deals",
            json={"title": "Gate Test Deal", "stage_id": st_disc, "amount": "15000.00"},
            headers=headers,
        )
    ).json()

    # Moving to stage 4 without tax_id_nit must return 422 AND X-Stage-Gate-Fields header
    move_resp = await client.post(
        f"/api/v1/deals/{deal['id']}/move-stage",
        json={"new_stage_id": st_neg},
        headers=headers,
    )
    assert move_resp.status_code == 422
    raw_header = move_resp.headers.get("X-Stage-Gate-Fields")
    assert raw_header is not None
    missing_fields = json.loads(raw_header)
    assert len(missing_fields) == 1
    assert missing_fields[0]["field_key"] == "tax_id_nit"
    assert missing_fields[0]["label"] == "NIT / Tax ID"
