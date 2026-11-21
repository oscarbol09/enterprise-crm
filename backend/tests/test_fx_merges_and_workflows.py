"""
Integration tests for multi-currency FX locking, non-destructive merges, task hygiene, and stage playbooks:
1. Multi-Currency Normalization Engine & Historical Exchange Rate Locking at Deal Close
2. Transparent Merged Entity ID Resolution (No 404 on Old Merged IDs), Account Merge & Soft-Delete Undo/Restore
3. Zombie Task Auto-Cancellation on Deal Close, Duplicate Task Prevention & Zombie Task Pruning
4. Stage-Gated Lazy Custom Field Validation (min_stage_position) & Anti-Garbage Placeholder Guard ("TBD", "N/A")
5. Rep Productivity Payback (Contextual Follow-up Draft & Stage Playbook Generator)
"""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from tests.conftest import register_and_login


async def test_multi_currency_normalization_and_historical_exchange_rate_lock(
    client: AsyncClient,
) -> None:
    auth = await register_and_login(client, slug="fx-corp", email="admin@fxcorp.io")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    stages = {s["name"]: s for s in (await client.get("/api/v1/deals/stages", headers=headers)).json()}

    # 1. Create a Deal in EUR (default reference rate 1.08 or custom explicit rate 1.10)
    eur_deal = (
        await client.post(
            "/api/v1/deals",
            headers=headers,
            json={
                "title": "Contrato Berlín GmbH",
                "stage_id": stages["Prospección"]["id"],
                "amount": "100000.00",
                "currency": "EUR",
                "exchange_rate_to_usd": "1.100000",
            },
        )
    ).json()
    assert eur_deal["currency"] == "EUR"
    assert float(eur_deal["exchange_rate_to_usd"]) == 1.1
    assert float(eur_deal["normalized_amount_usd"]) == 110000.0

    # 2. Create a Deal in MXN using built-in ISO reference rate (0.050000 -> 200,000 MXN = 10,000 USD)
    mxn_deal = (
        await client.post(
            "/api/v1/deals",
            headers=headers,
            json={
                "title": "Expansión Monterrey",
                "stage_id": stages["Calificación"]["id"],
                "amount": "200000.00",
                "currency": "MXN",
            },
        )
    ).json()
    assert mxn_deal["currency"] == "MXN"
    assert float(mxn_deal["normalized_amount_usd"]) == 10000.0

    # 3. Close the EUR deal as Closed Won -> locks closed_at and historical exchange rate
    won_resp = await client.post(
        f"/api/v1/deals/{eur_deal['id']}/move-stage",
        headers=headers,
        json={"new_stage_id": stages["Cierre Ganado"]["id"]},
    )
    assert won_resp.status_code == 200
    assert won_resp.json()["is_won"] is True
    assert won_resp.json()["closed_at"] is not None

    # 4. Attempting to alter exchange_rate_to_usd on a closed deal must be rejected with 409
    alter_fx_on_closed = await client.patch(
        f"/api/v1/deals/{eur_deal['id']}",
        headers=headers,
        json={"exchange_rate_to_usd": "1.250000"},
    )
    assert alter_fx_on_closed.status_code == 409


async def test_merged_entity_transparent_redirect_account_merge_and_soft_delete_restore(
    client: AsyncClient,
) -> None:
    auth = await register_and_login(client, slug="merge-restore", email="admin@mergerestore.io")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    stages = (await client.get("/api/v1/deals/stages", headers=headers)).json()

    # 1. Create two duplicate contacts and merge source into target
    c_target = (
        await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"first_name": "Elena", "last_name": "Vance", "email": "elena@vance.io"},
        )
    ).json()
    c_source = (
        await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"first_name": "Elena M.", "last_name": "Vance", "email": "evance.old@vance.io"},
        )
    ).json()

    merge_c = await client.post(
        f"/api/v1/contacts/{c_target['id']}/merge",
        headers=headers,
        json={"source_contact_id": c_source["id"]},
    )
    assert merge_c.status_code == 200

    # Fetching the OLD merged source UUID must transparently resolve to the target contact (no 404!)
    legacy_lookup = await client.get(f"/api/v1/contacts/{c_source['id']}", headers=headers)
    assert legacy_lookup.status_code == 200
    assert legacy_lookup.json()["id"] == c_target["id"]

    # 2. Soft-delete target contact, then restore it via POST /contacts/{id}/restore
    del_c = await client.delete(f"/api/v1/contacts/{c_target['id']}", headers=headers)
    assert del_c.status_code == 204
    assert (await client.get(f"/api/v1/contacts/{c_target['id']}", headers=headers)).status_code == 404

    restore_c = await client.post(f"/api/v1/contacts/{c_target['id']}/restore", headers=headers)
    assert restore_c.status_code == 200
    assert restore_c.json()["email"] == "elena@vance.io"

    # 3. Create two duplicate companies (Accounts), attach a deal to source, and merge accounts
    acc_target = (
        await client.post(
            "/api/v1/accounts",
            headers=headers,
            json={"name": "Vance Aerospace Inc.", "website": "https://vanceaero.com"},
        )
    ).json()
    acc_source = (
        await client.post(
            "/api/v1/accounts",
            headers=headers,
            json={"name": "Vance Aero LLC", "industry": "Aerospace"},
        )
    ).json()

    deal = (
        await client.post(
            "/api/v1/deals",
            headers=headers,
            json={
                "title": "Turbine Telemetry Suite",
                "stage_id": stages[0]["id"],
                "account_id": acc_source["id"],
                "amount": "75000.00",
            },
        )
    ).json()

    merge_acc = await client.post(
        f"/api/v1/accounts/{acc_target['id']}/merge",
        headers=headers,
        json={"source_account_id": acc_source["id"]},
    )
    assert merge_acc.status_code == 200
    assert merge_acc.json()["industry"] == "Aerospace"

    # Old account ID resolves transparently to target account
    old_acc_get = await client.get(f"/api/v1/accounts/{acc_source['id']}", headers=headers)
    assert old_acc_get.status_code == 200
    assert old_acc_get.json()["id"] == acc_target["id"]

    # Deal is now linked to acc_target
    deals_list = (await client.get("/api/v1/deals", headers=headers)).json()
    assert deals_list[0]["id"] == deal["id"]
    assert deals_list[0]["account_id"] == acc_target["id"]


async def test_zombie_task_auto_cancellation_on_deal_close_and_pruning_endpoint(
    client: AsyncClient,
) -> None:
    auth = await register_and_login(client, slug="zombie-tasks", email="admin@zombietasks.io")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    stages = {s["name"]: s for s in (await client.get("/api/v1/deals/stages", headers=headers)).json()}

    deal = (
        await client.post(
            "/api/v1/deals",
            headers=headers,
            json={
                "title": "Proyecto Piloto Q4",
                "stage_id": stages["Propuesta"]["id"],
                "amount": "32000.00",
            },
        )
    ).json()

    # Create a pending follow-up task on the deal
    future_due = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    task_on_deal = (
        await client.post(
            "/api/v1/tasks",
            headers=headers,
            json={
                "title": "Llamar para revisar propuesta",
                "priority": "high",
                "due_date": future_due,
                "deal_id": deal["id"],
            },
        )
    ).json()
    assert task_on_deal["status"] == "pending"

    # Move deal to Cierre Perdido -> pending tasks on that closed deal must be auto-cancelled!
    await client.post(
        f"/api/v1/deals/{deal['id']}/move-stage",
        headers=headers,
        json={
            "new_stage_id": stages["Cierre Perdido"]["id"],
            "loss_reason": "Cliente eligió solución interna",
        },
    )

    tasks_after_close = (await client.get("/api/v1/tasks", headers=headers)).json()
    matched_task = next(t for t in tasks_after_close if t["id"] == task_on_deal["id"])
    assert matched_task["status"] == "cancelled"

    # Create a stale overdue task (30 days in the past) and prune zombie tasks
    stale_due = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    stale_task = (
        await client.post(
            "/api/v1/tasks",
            headers=headers,
            json={
                "title": "Seguimiento antiguo olvidado",
                "priority": "low",
                "due_date": stale_due,
            },
        )
    ).json()

    prune_resp = await client.post(
        "/api/v1/tasks/prune-zombies",
        headers=headers,
        json={"max_overdue_days": 14},
    )
    assert prune_resp.status_code == 200
    assert prune_resp.json()["pruned_count"] >= 1

    all_tasks = (await client.get("/api/v1/tasks", headers=headers)).json()
    pruned = next(t for t in all_tasks if t["id"] == stale_task["id"])
    assert pruned["status"] == "cancelled"


async def test_stage_gated_lazy_custom_field_validation_and_anti_garbage_guard(
    client: AsyncClient,
) -> None:
    auth = await register_and_login(client, slug="lazy-gate", email="admin@lazygate.io")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    stages = {s["name"]: s for s in (await client.get("/api/v1/deals/stages", headers=headers)).json()}

    # Define a custom field 'tax_id_nit' that is NOT required at Discovery (position 1),
    # ONLY required when reaching Negociación (position >= 4)!
    cf_nit = await client.post(
        "/api/v1/custom-fields",
        headers=headers,
        json={
            "entity_type": "deal",
            "field_key": "tax_id_nit",
            "label": "RUC / NIT Fiscal del Cliente",
            "field_type": "text",
            "is_required": False,
            "min_stage_position": 4,
        },
    )
    assert cf_nit.status_code == 201, cf_nit.text
    assert cf_nit.json()["min_stage_position"] == 4

    # 1. Rep creates deal in Prospección (position 1) WITHOUT knowing tax_id_nit -> Succeeds (Zero friction!)
    deal = (
        await client.post(
            "/api/v1/deals",
            headers=headers,
            json={
                "title": "Oportunidad Rápida sin Fricción",
                "stage_id": stages["Prospección"]["id"],
                "amount": "45000.00",
            },
        )
    ).json()

    # 2. Moving to Calificación (position 2) without tax_id_nit -> Succeeds!
    move_cal = await client.post(
        f"/api/v1/deals/{deal['id']}/move-stage",
        headers=headers,
        json={"new_stage_id": stages["Calificación"]["id"]},
    )
    assert move_cal.status_code == 200

    # 3. Attempting to move to Negociación (position 4) without tax_id_nit -> Blocked with 422 stage gate!
    move_neg_blocked = await client.post(
        f"/api/v1/deals/{deal['id']}/move-stage",
        headers=headers,
        json={"new_stage_id": stages["Negociación"]["id"]},
    )
    assert move_neg_blocked.status_code == 422
    assert "tax_id_nit" in move_neg_blocked.json()["detail"]

    # 4. Rep tries to bypass validation with garbage placeholder "TBD" or "N/A" -> Blocked with 422!
    garbage_patch = await client.patch(
        f"/api/v1/deals/{deal['id']}",
        headers=headers,
        json={"metadata": {"tax_id_nit": "TBD"}},
    )
    assert garbage_patch.status_code == 422

    # 5. Rep provides real Tax ID and transitions to Negociación -> Succeeds!
    valid_patch = await client.patch(
        f"/api/v1/deals/{deal['id']}",
        headers=headers,
        json={"metadata": {"tax_id_nit": "901.452.881-9"}},
    )
    assert valid_patch.status_code == 200

    move_neg_ok = await client.post(
        f"/api/v1/deals/{deal['id']}/move-stage",
        headers=headers,
        json={"new_stage_id": stages["Negociación"]["id"]},
    )
    assert move_neg_ok.status_code == 200


async def test_rep_productivity_payback_playbook_generator(
    client: AsyncClient,
) -> None:
    auth = await register_and_login(client, slug="payback-crm", email="admin@payback.io")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    stages = {s["name"]: s for s in (await client.get("/api/v1/deals/stages", headers=headers)).json()}

    contact = (
        await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"first_name": "Camila", "last_name": "Ortega", "email": "camila@ortega.io"},
        )
    ).json()
    deal = (
        await client.post(
            "/api/v1/deals",
            headers=headers,
            json={
                "title": "Licencia Corporativa 200 Usuarios",
                "stage_id": stages["Propuesta"]["id"],
                "contact_id": contact["id"],
                "amount": "64000.00",
            },
        )
    ).json()

    playbook = await client.get(f"/api/v1/deals/{deal['id']}/playbook", headers=headers)
    assert playbook.status_code == 200
    data = playbook.json()
    assert data["stage_name"] == "Propuesta"
    assert "Camila" in data["suggested_email_body"]
    assert len(data["recommended_actions"]) >= 2
