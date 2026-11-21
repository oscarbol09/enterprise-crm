"""
Integration tests for B2B multi-entity graph, custom fields, SCD2 history, and RBAC:
1. Multi-Entity Graph Relationships (Company Affiliations & Deal Buying Committee Participants)
2. Dynamic Custom Fields Engine (Metadata Registry, Strict Type/Enum Validation, JSONB Filtering)
3. Activity Timeline Roll-Up, Cursor Pagination, Soft-Delete History Preservation, Contact Merge,
   SCD Type 2 Deal Stage History, and System Entity Audit Trail
4. Email Sync Engine (RFC 5322 Message-ID Deduplication, Threading, Noise Filtering, Internal Domain Guard)
5. Granular RBAC & Ownership / Team Visibility Scoping
"""

import uuid
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from src.models.entities import OutboxEvent, User

from tests.conftest import create_role_user_and_login, register_and_login


async def test_multi_entity_company_affiliations_and_deal_buying_committee(
    client: AsyncClient,
) -> None:
    auth = await register_and_login(client, slug="graph-b2b", email="admin@graphb2b.io")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    # Create two companies (e.g. a parent holding and a portfolio startup)
    acc_1 = (
        await client.post(
            "/api/v1/accounts",
            headers=headers,
            json={"name": "Apex Ventures", "industry": "Venture Capital", "website": "https://apex.vc"},
        )
    ).json()
    acc_2 = (
        await client.post(
            "/api/v1/accounts",
            headers=headers,
            json={"name": "Nebula Cloud", "industry": "SaaS", "website": "https://nebulacloud.io"},
        )
    ).json()

    # Create two contacts: an advisor affiliated with both companies, and a CFO at Nebula Cloud
    c_advisor = (
        await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={
                "first_name": "Martín",
                "last_name": "Salazar",
                "email": "martin@apex.vc",
                "account_id": acc_1["id"],
                "job_title": "Managing Partner",
            },
        )
    ).json()
    c_cfo = (
        await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={
                "first_name": "Elena",
                "last_name": "Ríos",
                "email": "elena.rios@nebulacloud.io",
                "account_id": acc_2["id"],
                "job_title": "CFO",
            },
        )
    ).json()

    # Link Martín as an External Board Advisor to Nebula Cloud (multi-company affiliation)
    aff_resp = await client.post(
        f"/api/v1/accounts/{acc_2['id']}/affiliations",
        headers=headers,
        json={
            "contact_id": c_advisor["id"],
            "role_title": "Board Advisor",
            "department": "Board of Directors",
            "is_primary": False,
        },
    )
    assert aff_resp.status_code == 201, aff_resp.text
    assert aff_resp.json()["role_title"] == "Board Advisor"

    # List affiliations for Martín -> should return both Apex Ventures (primary) and Nebula Cloud
    contact_affs = await client.get(f"/api/v1/contacts/{c_advisor['id']}/affiliations", headers=headers)
    assert contact_affs.status_code == 200
    assert len(contact_affs.json()) == 2

    # Create a Deal for Nebula Cloud with Martín as primary contact
    stages = (await client.get("/api/v1/deals/stages", headers=headers)).json()
    deal = (
        await client.post(
            "/api/v1/deals",
            headers=headers,
            json={
                "title": "Nebula Enterprise Platform",
                "stage_id": stages[0]["id"],
                "account_id": acc_2["id"],
                "contact_id": c_advisor["id"],
                "amount": "85000.00",
            },
        )
    ).json()

    # Add Elena (CFO) to the Deal buying committee as economic_buyer
    add_part = await client.post(
        f"/api/v1/deals/{deal['id']}/participants",
        headers=headers,
        json={
            "contact_id": c_cfo["id"],
            "buying_role": "economic_buyer",
            "is_primary": False,
            "notes": "Approves budgets > $50k",
        },
    )
    assert add_part.status_code == 201, add_part.text

    # List deal participants -> should include Martín (auto-enrolled primary champion) and Elena (economic_buyer)
    parts = await client.get(f"/api/v1/deals/{deal['id']}/participants", headers=headers)
    assert parts.status_code == 200
    roles_by_contact = {p["contact_id"]: p["buying_role"] for p in parts.json()}
    assert roles_by_contact[c_advisor["id"]] == "champion"
    assert roles_by_contact[c_cfo["id"]] == "economic_buyer"


async def test_custom_fields_metadata_registry_validation_and_filtering(
    client: AsyncClient,
) -> None:
    auth = await register_and_login(client, slug="cf-tenant", email="admin@cftenant.io")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    stages = (await client.get("/api/v1/deals/stages", headers=headers)).json()

    # 1. Define custom fields for 'deal' and 'contact'
    cf_arr = await client.post(
        "/api/v1/custom-fields",
        headers=headers,
        json={
            "entity_type": "deal",
            "field_key": "contract_months",
            "label": "Duración del Contrato (Meses)",
            "field_type": "number",
            "is_required": True,
        },
    )
    assert cf_arr.status_code == 201, cf_arr.text

    cf_erp = await client.post(
        "/api/v1/custom-fields",
        headers=headers,
        json={
            "entity_type": "contact",
            "field_key": "current_erp",
            "label": "ERP Actual",
            "field_type": "select",
            "is_required": False,
            "allowed_values": ["SAP", "NetSuite", "Odoo"],
        },
    )
    assert cf_erp.status_code == 201, cf_erp.text

    # 2. Creating a Deal without required custom field 'contract_months' -> 422
    bad_deal_missing = await client.post(
        "/api/v1/deals",
        headers=headers,
        json={
            "title": "Deal sin custom field obligatorio",
            "stage_id": stages[0]["id"],
            "amount": "15000.00",
        },
    )
    assert bad_deal_missing.status_code == 422

    # 3. Creating a Deal with wrong type (string instead of number) -> 422
    bad_deal_type = await client.post(
        "/api/v1/deals",
        headers=headers,
        json={
            "title": "Deal con tipo inválido",
            "stage_id": stages[0]["id"],
            "amount": "15000.00",
            "metadata": {"contract_months": "doce meses"},
        },
    )
    assert bad_deal_type.status_code == 422

    # 4. Creating a Deal with valid custom field -> 201
    good_deal = await client.post(
        "/api/v1/deals",
        headers=headers,
        json={
            "title": "Deal Anual Validado",
            "stage_id": stages[0]["id"],
            "amount": "36000.00",
            "metadata": {"contract_months": 24},
        },
    )
    assert good_deal.status_code == 201, good_deal.text
    assert good_deal.json()["metadata"]["contract_months"] == 24

    # 5. Creating a Contact with invalid enum option -> 422
    bad_contact_enum = await client.post(
        "/api/v1/contacts",
        headers=headers,
        json={
            "first_name": "Pedro",
            "last_name": "Lara",
            "email": "pedro@lara.io",
            "metadata": {"current_erp": "ExcelCasero"},
        },
    )
    assert bad_contact_enum.status_code == 422

    # 6. Creating and updating Contact with valid enum option -> 201 & PATCH 200
    good_contact = await client.post(
        "/api/v1/contacts",
        headers=headers,
        json={
            "first_name": "Pedro",
            "last_name": "Lara",
            "email": "pedro@lara.io",
            "metadata": {"current_erp": "SAP"},
        },
    )
    assert good_contact.status_code == 201
    cid = good_contact.json()["id"]

    patch_cf = await client.patch(
        f"/api/v1/contacts/{cid}",
        headers=headers,
        json={"metadata": {"current_erp": "NetSuite"}},
    )
    assert patch_cf.status_code == 200
    assert patch_cf.json()["metadata"]["current_erp"] == "NetSuite"

    # 7. Filter contacts by custom field key/value
    filtered = await client.get("/api/v1/contacts?cf_key=current_erp&cf_value=NetSuite", headers=headers)
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["id"] == cid


async def test_activity_rollup_scd2_stage_history_soft_delete_merge_and_cursor_pagination(
    client: AsyncClient,
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    auth = await register_and_login(client, slug="rollup-corp", email="admin@rollup.io")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    stages = {s["name"]: s for s in (await client.get("/api/v1/deals/stages", headers=headers)).json()}

    account = (
        await client.post(
            "/api/v1/accounts",
            headers=headers,
            json={"name": "Global Logistics S.A.", "website": "https://globallogistics.io"},
        )
    ).json()

    contact_primary = (
        await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={
                "first_name": "Ana",
                "last_name": "Silva",
                "email": "ana.silva@globallogistics.io",
                "account_id": account["id"],
            },
        )
    ).json()

    contact_duplicate = (
        await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={
                "first_name": "Ana M.",
                "last_name": "Silva",
                "email": "asilva.personal@gmail.com",
            },
        )
    ).json()

    deal = (
        await client.post(
            "/api/v1/deals",
            headers=headers,
            json={
                "title": "Flota Telemetría 2027",
                "stage_id": stages["Prospección"]["id"],
                "account_id": account["id"],
                "contact_id": contact_duplicate["id"],
                "amount": "110000.00",
                "expected_close_date": str(date.today() + timedelta(days=15)),
            },
        )
    ).json()

    # Log an interaction directly on the duplicate contact (without passing account_id)
    inter_1 = await client.post(
        "/api/v1/interactions",
        headers=headers,
        json={
            "contact_id": contact_duplicate["id"],
            "deal_id": deal["id"],
            "type": "call",
            "direction": "inbound",
            "subject": "Llamada inicial de descubrimiento",
            "content_body": "Confirmaron presupuesto para Q1.",
        },
    )
    assert inter_1.status_code == 201, inter_1.text
    # Account ID must be auto-resolved from the deal!
    assert inter_1.json()["account_id"] == account["id"]

    # Merge contact_duplicate into contact_primary
    merge_resp = await client.post(
        f"/api/v1/contacts/{contact_primary['id']}/merge",
        headers=headers,
        json={"source_contact_id": contact_duplicate["id"]},
    )
    assert merge_resp.status_code == 200, merge_resp.text
    merged_contact = merge_resp.json()
    assert "asilva.personal@gmail.com" in merged_contact["metadata"].get("secondary_emails", [])

    # Duplicate contact should no longer appear in active contacts list
    active_contacts = (await client.get("/api/v1/contacts", headers=headers)).json()
    assert len(active_contacts) == 1
    assert active_contacts[0]["id"] == contact_primary["id"]

    # Deal and Interaction must now be re-linked to contact_primary
    deal_timeline = (await client.get(f"/api/v1/deals/{deal['id']}/interactions", headers=headers)).json()
    assert len(deal_timeline) >= 1
    assert deal_timeline[0]["contact_id"] == contact_primary["id"]

    # Move deal across stages and push expected_close_date to verify SCD Type 2 Stage History & Slippage
    await client.post(
        f"/api/v1/deals/{deal['id']}/move-stage",
        headers=headers,
        json={"new_stage_id": stages["Calificación"]["id"]},
    )
    await client.post(
        f"/api/v1/deals/{deal['id']}/move-stage",
        headers=headers,
        json={"new_stage_id": stages["Propuesta"]["id"]},
    )

    stage_hist = await client.get(f"/api/v1/deals/{deal['id']}/stage-history", headers=headers)
    assert stage_hist.status_code == 200
    hist_items = stage_hist.json()
    # Initial stage (Prospección, closed out) -> Calificación (closed out) -> Propuesta (active, exited_at=None)
    assert len(hist_items) == 3
    closed_entries = [h for h in hist_items if h["exited_at"] is not None]
    active_entries = [h for h in hist_items if h["exited_at"] is None]
    assert len(closed_entries) == 2
    assert len(active_entries) == 1
    assert active_entries[0]["to_stage_id"] == stages["Propuesta"]["id"]

    # Account Roll-Up Timeline must show all interactions (calls + stage transitions) with cursor pagination
    acc_timeline_page1 = await client.get(
        f"/api/v1/accounts/{account['id']}/timeline?limit=2", headers=headers
    )
    assert acc_timeline_page1.status_code == 200
    page1_data = acc_timeline_page1.json()
    assert len(page1_data["items"]) == 2
    assert page1_data["next_cursor"] is not None

    acc_timeline_page2 = await client.get(
        f"/api/v1/accounts/{account['id']}/timeline?limit=2&cursor={page1_data['next_cursor']}",
        headers=headers,
    )
    assert acc_timeline_page2.status_code == 200
    page2_data = acc_timeline_page2.json()
    assert len(page2_data["items"]) >= 1
    page1_ids = {item["id"] for item in page1_data["items"]}
    page2_ids = {item["id"] for item in page2_data["items"]}
    assert page1_ids.isdisjoint(page2_ids)

    # Soft-deleting contact_primary must NOT delete the Deal's interaction history!
    del_resp = await client.delete(f"/api/v1/contacts/{contact_primary['id']}", headers=headers)
    assert del_resp.status_code == 204
    surviving_timeline = (await client.get(f"/api/v1/deals/{deal['id']}/interactions", headers=headers)).json()
    assert len(surviving_timeline) >= 3

    # Verify OutboxEvent decimal precision (string representation + integer cents)
    async with test_session_factory() as session:
        deal_events = list(
            (
                await session.scalars(
                    select(OutboxEvent).where(OutboxEvent.aggregate_id == uuid.UUID(deal["id"]))
                )
            ).all()
        )
        assert any(evt.payload.get("amount_decimal") == "110000.00" for evt in deal_events)
        assert any(evt.payload.get("amount_cents") == 11000000 for evt in deal_events)
        assert all(isinstance(evt.payload.get("amount"), str) for evt in deal_events)

    # Verify System Entity Audit Logs captured the MERGE and SOFT_DELETE operations
    audit_resp = await client.get("/api/v1/audit-logs?entity_type=contact", headers=headers)
    assert audit_resp.status_code == 200
    actions = {row["action"] for row in audit_resp.json()}
    assert "MERGE" in actions
    assert "SOFT_DELETE" in actions


async def test_email_sync_deduplication_noise_filtering_and_internal_domain_privacy(
    client: AsyncClient,
) -> None:
    auth = await register_and_login(client, slug="sync-corp", email="admin@synccorp.io")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    # Configure internal domain for privacy auto-exclusion
    settings_resp = await client.patch(
        "/api/v1/auth/workspace-settings",
        headers=headers,
        json={"internal_domains": ["synccorp.io"]},
    )
    assert settings_resp.status_code == 200

    acc = (
        await client.post(
            "/api/v1/accounts",
            headers=headers,
            json={"name": "ClientCo", "website": "https://clientco.com"},
        )
    ).json()
    contact = (
        await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={
                "first_name": " Roberto",
                "last_name": "Díaz",
                "email": "roberto@clientco.com",
                "account_id": acc["id"],
            },
        )
    ).json()

    # 1. Ingest inbound email from client CC'd to two internal reps (First delivery via Rep 1's mailbox)
    msg_id = "<CABc123456789@mail.clientco.com>"
    sync_1 = await client.post(
        "/api/v1/communications/email-sync",
        headers=headers,
        json={
            "rfc_message_id": msg_id,
            "thread_id": "thread-clientco-01",
            "mailbox_email": "rep1@synccorp.io",
            "sender_email": "roberto@clientco.com",
            "recipient_emails": ["rep1@synccorp.io", "rep2@synccorp.io"],
            "subject": "Re: Propuesta Comercial Enterprise",
            "body_text": "Adjunto comentarios del equipo legal sobre el contrato.",
            "headers": {},
        },
    )
    assert sync_1.status_code == 201, sync_1.text
    assert sync_1.json()["status"] == "ingested"
    interaction_id = sync_1.json()["interaction_id"]

    # 2. Same email arrives from Rep 2's mailbox webhook -> must deduplicate by Message-ID!
    sync_2 = await client.post(
        "/api/v1/communications/email-sync",
        headers=headers,
        json={
            "rfc_message_id": msg_id,
            "thread_id": "thread-clientco-01",
            "mailbox_email": "rep2@synccorp.io",
            "sender_email": "roberto@clientco.com",
            "recipient_emails": ["rep1@synccorp.io", "rep2@synccorp.io"],
            "subject": "Re: Propuesta Comercial Enterprise",
            "body_text": "Adjunto comentarios del equipo legal sobre el contrato.",
            "headers": {},
        },
    )
    assert sync_2.status_code == 200, sync_2.text
    assert sync_2.json()["status"] == "deduplicated"
    assert sync_2.json()["interaction_id"] == interaction_id
    assert sorted(sync_2.json()["synced_mailboxes"]) == ["rep1@synccorp.io", "rep2@synccorp.io"]

    # Verify only ONE interaction was created on the contact timeline
    c_timeline = (await client.get(f"/api/v1/contacts/{contact['id']}/timeline", headers=headers)).json()
    assert len(c_timeline["items"]) == 1

    # 3. Auto-responder (Out of Office) -> must be filtered as noise
    ooo_sync = await client.post(
        "/api/v1/communications/email-sync",
        headers=headers,
        json={
            "rfc_message_id": "<ooo-999@mail.clientco.com>",
            "mailbox_email": "rep1@synccorp.io",
            "sender_email": "roberto@clientco.com",
            "recipient_emails": ["rep1@synccorp.io"],
            "subject": "Out of Office: Roberto Díaz",
            "body_text": "Estaré fuera de la oficina hasta el lunes.",
            "headers": {"Auto-Submitted": "auto-replied"},
        },
    )
    assert ooo_sync.status_code == 200
    assert ooo_sync.json()["status"] == "filtered_noise"

    # 4. Internal chatter or HR/Payroll email -> must be excluded for privacy
    internal_sync = await client.post(
        "/api/v1/communications/email-sync",
        headers=headers,
        json={
            "rfc_message_id": "<internal-hr-1@synccorp.io>",
            "mailbox_email": "admin@synccorp.io",
            "sender_email": "admin@synccorp.io",
            "recipient_emails": ["hr@synccorp.io", "rep1@synccorp.io"],
            "subject": "Revisión confidencial de nómina",
            "body_text": "Confidencial.",
            "headers": {},
        },
    )
    assert internal_sync.status_code == 200
    assert internal_sync.json()["status"] == "excluded_internal_or_sensitive"


async def test_hierarchical_and_owner_only_rbac_visibility_scoping(
    client: AsyncClient,
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    admin = await register_and_login(client, slug="rbac-hierarchy", email="admin@rbachier.io")
    tenant_id = uuid.UUID(admin["user"]["tenant_id"])
    team_north = uuid.uuid4()
    team_south = uuid.uuid4()

    rep_1 = await create_role_user_and_login(
        client, test_session_factory, tenant_id, "rbac-hierarchy", "rep1@rbachier.io", "sales_rep"
    )
    rep_2 = await create_role_user_and_login(
        client, test_session_factory, tenant_id, "rbac-hierarchy", "rep2@rbachier.io", "sales_rep"
    )

    # Assign teams
    async with test_session_factory() as session:
        u1 = await session.scalar(select(User).where(User.id == uuid.UUID(rep_1["user"]["id"])))
        u2 = await session.scalar(select(User).where(User.id == uuid.UUID(rep_2["user"]["id"])))
        assert u1 and u2
        u1.team_id = team_north
        u2.team_id = team_south
        await session.commit()

    h_admin = {"Authorization": f"Bearer {admin['access_token']}"}
    h_rep1 = {"Authorization": f"Bearer {rep_1['access_token']}"}
    h_rep2 = {"Authorization": f"Bearer {rep_2['access_token']}"}

    # Rep 1 and Rep 2 each create their own Contact
    c1 = (
        await client.post(
            "/api/v1/contacts",
            headers=h_rep1,
            json={"first_name": "North", "last_name": "Lead", "email": "north@client.io"},
        )
    ).json()
    c2 = (
        await client.post(
            "/api/v1/contacts",
            headers=h_rep2,
            json={"first_name": "South", "last_name": "Lead", "email": "south@client.io"},
        )
    ).json()

    # Enable owner_only visibility and owner write guard on workspace
    cfg = await client.patch(
        "/api/v1/auth/workspace-settings",
        headers=h_admin,
        json={"record_visibility_mode": "owner_only", "enforce_owner_write_guard": True},
    )
    assert cfg.status_code == 200

    # Rep 1 listing contacts sees ONLY their own contact (North Lead)
    rep1_list = (await client.get("/api/v1/contacts", headers=h_rep1)).json()
    assert [c["id"] for c in rep1_list] == [c1["id"]]

    # Rep 1 attempting to PATCH Rep 2's contact is blocked (403 or 404 due to visibility scope)
    rep1_hijack = await client.patch(
        f"/api/v1/contacts/{c2['id']}",
        headers=h_rep1,
        json={"job_title": "Hijacked"},
    )
    assert rep1_hijack.status_code in (403, 404)

    # Admin still sees both contacts
    admin_list = (await client.get("/api/v1/contacts", headers=h_admin)).json()
    assert len(admin_list) == 2

    # Switch visibility mode to 'team' and add a teammate in team_north
    rep_1b = await create_role_user_and_login(
        client, test_session_factory, tenant_id, "rbac-hierarchy", "rep1b@rbachier.io", "sales_rep"
    )
    async with test_session_factory() as session:
        u1b = await session.scalar(select(User).where(User.id == uuid.UUID(rep_1b["user"]["id"])))
        assert u1b
        u1b.team_id = team_north
        await session.commit()

    h_rep1b = {"Authorization": f"Bearer {rep_1b['access_token']}"}
    await client.patch(
        "/api/v1/auth/workspace-settings",
        headers=h_admin,
        json={"record_visibility_mode": "team", "enforce_owner_write_guard": False},
    )
    ws_get = await client.get("/api/v1/auth/workspace-settings", headers=h_rep1b)
    assert ws_get.status_code == 200
    assert ws_get.json()["record_visibility_mode"] == "team"

    # Rep 1b (same team_north as Rep 1) can see Rep 1's contact, but NOT Rep 2's (team_south)
    team_visible = (await client.get("/api/v1/contacts", headers=h_rep1b)).json()
    assert [c["id"] for c in team_visible] == [c1["id"]]


async def test_custom_field_types_deal_slippage_and_email_thread_domain_matching(
    client: AsyncClient,
) -> None:
    auth = await register_and_login(client, slug="cf-edge", email="admin@cfedge.io")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    stages = (await client.get("/api/v1/deals/stages", headers=headers)).json()

    # Register boolean, date, multi_select, and text custom fields
    for spec in [
        {
            "entity_type": "account",
            "field_key": "is_regulated",
            "label": "Regulado",
            "field_type": "boolean",
        },
        {
            "entity_type": "account",
            "field_key": "renewal_date",
            "label": "Renovación",
            "field_type": "date",
        },
        {
            "entity_type": "account",
            "field_key": "regions",
            "label": "Regiones",
            "field_type": "multi_select",
            "allowed_values": ["LATAM", "EMEA", "NA"],
        },
        {
            "entity_type": "account",
            "field_key": "notes_tag",
            "label": "Tag",
            "field_type": "text",
        },
    ]:
        r = await client.post("/api/v1/custom-fields", headers=headers, json=spec)
        assert r.status_code == 201

    # Duplicate custom field key returns 409; select without allowed_values returns 422
    assert (
        await client.post(
            "/api/v1/custom-fields",
            headers=headers,
            json={
                "entity_type": "account",
                "field_key": "is_regulated",
                "label": "Dup",
                "field_type": "boolean",
            },
        )
    ).status_code == 409
    assert (
        await client.post(
            "/api/v1/custom-fields",
            headers=headers,
            json={
                "entity_type": "account",
                "field_key": "bad_select",
                "label": "Bad",
                "field_type": "select",
                "allowed_values": [],
            },
        )
    ).status_code == 422

    # List and delete a custom field
    cf_list = (await client.get("/api/v1/custom-fields?entity_type=account", headers=headers)).json()
    assert len(cf_list) == 4
    tag_cf_id = next(c["id"] for c in cf_list if c["field_key"] == "notes_tag")
    assert (await client.delete(f"/api/v1/custom-fields/{tag_cf_id}", headers=headers)).status_code == 204

    # Invalid boolean, invalid date, invalid multi_select on Account -> 422
    assert (
        await client.post(
            "/api/v1/accounts",
            headers=headers,
            json={"name": "BadBool", "metadata": {"is_regulated": "yes"}},
        )
    ).status_code == 422
    assert (
        await client.post(
            "/api/v1/accounts",
            headers=headers,
            json={"name": "BadDate", "metadata": {"renewal_date": "31-02-2027"}},
        )
    ).status_code == 422
    assert (
        await client.post(
            "/api/v1/accounts",
            headers=headers,
            json={"name": "BadMulti", "metadata": {"regions": ["APAC"]}},
        )
    ).status_code == 422

    # Valid Account creation & PATCH + custom field filter
    acc = (
        await client.post(
            "/api/v1/accounts",
            headers=headers,
            json={
                "name": "Andina FinTech",
                "website": "https://andinafintech.co",
                "metadata": {
                    "is_regulated": True,
                    "renewal_date": "2027-06-30",
                    "regions": ["LATAM", "NA"],
                },
            },
        )
    ).json()
    acc_patch = await client.patch(
        f"/api/v1/accounts/{acc['id']}",
        headers=headers,
        json={"industry": "Banking", "metadata": {"regions": ["LATAM"]}},
    )
    assert acc_patch.status_code == 200
    acc_filtered = (
        await client.get("/api/v1/accounts?q=Andina&cf_key=regions&cf_value=LATAM", headers=headers)
    ).json()
    assert len(acc_filtered) == 1

    # Deal expected_close_date push increments close_date_push_count (Deal Slippage metric)
    initial_close = date.today() + timedelta(days=10)
    slipped_close = date.today() + timedelta(days=40)
    deal = (
        await client.post(
            "/api/v1/deals",
            headers=headers,
            json={
                "title": "Core Banking Upgrade",
                "stage_id": stages[0]["id"],
                "account_id": acc["id"],
                "amount": "200000.00",
                "expected_close_date": str(initial_close),
            },
        )
    ).json()
    assert deal["close_date_push_count"] == 0

    patched_deal = (
        await client.patch(
            f"/api/v1/deals/{deal['id']}",
            headers=headers,
            json={"expected_close_date": str(slipped_close)},
        )
    ).json()
    assert patched_deal["close_date_push_count"] == 1

    # Email sync domain resolution against Account.website when contact does not exist yet
    email_domain_match = await client.post(
        "/api/v1/communications/email-sync",
        headers=headers,
        json={
            "rfc_message_id": "<domain-match-01@andinafintech.co>",
            "thread_id": "th-andina-1",
            "mailbox_email": "admin@cfedge.io",
            "sender_email": "unknown.exec@andinafintech.co",
            "recipient_emails": ["admin@cfedge.io"],
            "subject": "Consulta sobre integración Core Banking",
            "body_text": "Hola, vimos su propuesta.",
            "headers": {},
        },
    )
    assert email_domain_match.status_code == 201
    assert email_domain_match.json()["account_id"] == acc["id"]


async def test_master_list_keyset_cursor_pagination(client: AsyncClient) -> None:
    """Verifies O(1) composite keyset cursor pagination via X-Next-Cursor across contacts, accounts, and deals."""
    auth = await register_and_login(client, slug="cursor-corp", email="admin@cursor.io")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    stages = (await client.get("/api/v1/deals/stages", headers=headers)).json()

    # Seed 3 contacts, 3 accounts, 3 deals
    for idx in range(3):
        await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"first_name": f"User{idx}", "last_name": "Cursor", "email": f"u{idx}@cursor.io"},
        )
        await client.post(
            "/api/v1/accounts",
            headers=headers,
            json={"name": f"Company {idx}"},
        )
        await client.post(
            "/api/v1/deals",
            headers=headers,
            json={
                "title": f"Deal Cursor {idx}",
                "stage_id": stages[0]["id"],
                "amount": f"{(idx + 1) * 1000}.00",
            },
        )

    for endpoint in ("/api/v1/contacts", "/api/v1/accounts", "/api/v1/deals"):
        p1 = await client.get(f"{endpoint}?limit=2", headers=headers)
        assert p1.status_code == 200
        items1 = p1.json()
        assert len(items1) == 2
        next_cursor = p1.headers.get("X-Next-Cursor")
        assert next_cursor is not None

        p2 = await client.get(f"{endpoint}?limit=2&cursor={next_cursor}", headers=headers)
        assert p2.status_code == 200
        items2 = p2.json()
        assert len(items2) == 1
        assert "X-Next-Cursor" not in p2.headers
        assert {x["id"] for x in items1}.isdisjoint({x["id"] for x in items2})


