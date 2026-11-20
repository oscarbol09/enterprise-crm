"""
Integration Tests for Contacts, Accounts, Tasks, Deals Pipeline, Stage Transitions & RBAC.
"""

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from src.models.entities import Interaction, OutboxEvent

from tests.conftest import create_role_user_and_login, register_and_login


async def test_contacts_crud_dedup_search_and_tenant_isolation(
    client: AsyncClient,
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant_a = await register_and_login(client, slug="tenant-a", email="a@tenant.io")
    tenant_b = await register_and_login(client, slug="tenant-b", email="b@tenant.io")
    readonly_a = await create_role_user_and_login(
        client,
        test_session_factory,
        uuid.UUID(tenant_a["user"]["tenant_id"]),
        "tenant-a",
        "ro@tenant.io",
        "readonly",
    )

    headers_a = {"Authorization": f"Bearer {tenant_a['access_token']}"}
    headers_b = {"Authorization": f"Bearer {tenant_b['access_token']}"}
    headers_ro = {"Authorization": f"Bearer {readonly_a['access_token']}"}

    # Readonly cannot create contacts
    ro_create = await client.post(
        "/api/v1/contacts",
        headers=headers_ro,
        json={"first_name": "Blocked", "last_name": "User", "email": "blocked@x.io"},
    )
    assert ro_create.status_code == 403

    # Create contact in Tenant A
    create_resp = await client.post(
        "/api/v1/contacts",
        headers=headers_a,
        json={
            "first_name": "Lucía",
            "last_name": "Fernández",
            "email": "LUCIA@CLIENT.IO",
            "job_title": "CTO",
            "lifecycle_stage": "sales_qualified",
        },
    )
    assert create_resp.status_code == 201
    contact_id = create_resp.json()["id"]
    assert create_resp.json()["email"] == "lucia@client.io"

    # Duplicate email in Tenant A returns 409
    dup = await client.post(
        "/api/v1/contacts",
        headers=headers_a,
        json={"first_name": "Dup", "last_name": "Lead", "email": "lucia@client.io"},
    )
    assert dup.status_code == 409

    # Search filter works within Tenant A
    filtered = await client.get("/api/v1/contacts?q=CTO&lifecycle_stage=sales_qualified", headers=headers_a)
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1

    # Tenant B cannot read or list Tenant A's contact
    cross_get = await client.get(f"/api/v1/contacts/{contact_id}", headers=headers_b)
    assert cross_get.status_code == 404
    cross_list = await client.get("/api/v1/contacts", headers=headers_b)
    assert cross_list.json() == []

    # Patch and delete contact in Tenant A
    patch_resp = await client.patch(
        f"/api/v1/contacts/{contact_id}",
        headers=headers_a,
        json={"lifecycle_stage": "customer", "lead_score": "95.50"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["lifecycle_stage"] == "customer"

    del_resp = await client.delete(f"/api/v1/contacts/{contact_id}", headers=headers_a)
    assert del_resp.status_code == 204


async def test_deals_pipeline_stage_transitions_forecasting_and_loss_reason(
    client: AsyncClient,
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    auth = await register_and_login(client, slug="deals-corp", email="admin@deals.io")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    stages_resp = await client.get("/api/v1/deals/stages", headers=headers)
    assert stages_resp.status_code == 200
    stages = stages_resp.json()
    assert len(stages) == 6
    stage_by_name = {s["name"]: s for s in stages}

    deal_resp = await client.post(
        "/api/v1/deals",
        headers=headers,
        json={
            "title": "Enterprise SaaS Rollout",
            "stage_id": stage_by_name["Prospección"]["id"],
            "amount": "90000.00",
            "currency": "USD",
        },
    )
    assert deal_resp.status_code == 201
    deal_id = deal_resp.json()["id"]
    assert deal_resp.json()["forecast_category"] == "pipeline"

    # Transition to Negociación (0.80 -> forecast commit)
    move_neg = await client.post(
        f"/api/v1/deals/{deal_id}/move-stage",
        headers=headers,
        json={"new_stage_id": stage_by_name["Negociación"]["id"]},
    )
    assert move_neg.status_code == 200
    assert move_neg.json()["forecast_category"] == "commit"
    assert float(move_neg.json()["win_probability"]) == 0.8

    # Transition to Closed Lost without loss_reason -> 422
    move_lost_no_reason = await client.post(
        f"/api/v1/deals/{deal_id}/move-stage",
        headers=headers,
        json={"new_stage_id": stage_by_name["Cierre Perdido"]["id"]},
    )
    assert move_lost_no_reason.status_code == 422

    # Transition to Closed Lost with loss_reason -> 200
    move_lost_ok = await client.post(
        f"/api/v1/deals/{deal_id}/move-stage",
        headers=headers,
        json={
            "new_stage_id": stage_by_name["Cierre Perdido"]["id"],
            "loss_reason": "Presupuesto congelado Q4",
        },
    )
    assert move_lost_ok.status_code == 200
    assert move_lost_ok.json()["is_lost"] is True
    assert move_lost_ok.json()["forecast_category"] == "omitted"

    # Verify interaction history & outbox events were recorded atomically
    timeline = await client.get(f"/api/v1/deals/{deal_id}/interactions", headers=headers)
    assert timeline.status_code == 200
    assert len(timeline.json()) == 2

    async with test_session_factory() as session:
        events = list((await session.scalars(select(OutboxEvent))).all())
        assert len(events) == 3  # DealCreated + 2x DealStageChanged
        interactions = list((await session.scalars(select(Interaction))).all())
        assert len(interactions) == 2


async def test_accounts_and_tasks_crud(client: AsyncClient) -> None:
    auth = await register_and_login(client, slug="ops-crm", email="ops@ops.io")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    acc = await client.post(
        "/api/v1/accounts",
        headers=headers,
        json={"name": "Andes Cloud", "industry": "Cloud", "employee_count": 120},
    )
    assert acc.status_code == 201
    acc_id = acc.json()["id"]

    acc_list = await client.get("/api/v1/accounts", headers=headers)
    assert len(acc_list.json()) == 1

    due = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    task = await client.post(
        "/api/v1/tasks",
        headers=headers,
        json={"title": "Enviar NDA firmado", "priority": "high", "due_date": due},
    )
    assert task.status_code == 201
    task_id = task.json()["id"]

    completed = await client.patch(
        f"/api/v1/tasks/{task_id}",
        headers=headers,
        json={"status": "completed"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["completed_at"] is not None
    assert acc_id is not None
