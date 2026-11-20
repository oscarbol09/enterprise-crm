"""
Additional Edge-Case, Error-Path & Resilience Tests across API, Services, and Middleware.
"""

import types
import uuid

import litellm
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from src.core.config import settings
from src.core.database import tenant_session_scope
from src.core.rate_limit import set_redis_client
from src.models.entities import TenantLLMCredential
from src.services.ai_service import AIProviderError, MultiModelRouter, parse_llm_analysis_json
from src.services.mcp_crm_server import MCPAgentExecutionEngine

from tests.conftest import register_and_login


async def test_health_correlation_id_and_security_headers(client: AsyncClient) -> None:
    resp = await client.get("/health", headers={"X-Correlation-ID": "corr-test-123"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
    assert resp.headers["X-Correlation-ID"] == "corr-test-123"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


async def test_contacts_deals_accounts_tasks_404_and_bootstrap_paths(client: AsyncClient) -> None:
    auth = await register_and_login(client, slug="edge-corp", email="admin@edge.io")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    missing_id = str(uuid.uuid4())

    assert (await client.get(f"/api/v1/contacts/{missing_id}", headers=headers)).status_code == 404
    assert (
        await client.patch(f"/api/v1/contacts/{missing_id}", headers=headers, json={"first_name": "X"})
    ).status_code == 404
    assert (await client.delete(f"/api/v1/contacts/{missing_id}", headers=headers)).status_code == 404

    assert (
        await client.post("/api/v1/deals", headers=headers, json={"title": "Bad", "stage_id": missing_id})
    ).status_code == 400
    assert (
        await client.post(
            f"/api/v1/deals/{missing_id}/move-stage", headers=headers, json={"new_stage_id": missing_id}
        )
    ).status_code == 404
    assert (await client.get(f"/api/v1/deals/{missing_id}/interactions", headers=headers)).status_code == 404
    assert (await client.post("/api/v1/deals/pipelines/bootstrap", headers=headers)).status_code == 201

    assert (
        await client.post(
            "/api/v1/accounts", headers=headers, json={"name": "Child", "parent_account_id": missing_id}
        )
    ).status_code == 404
    assert (
        await client.post(
            "/api/v1/tasks",
            headers=headers,
            json={"title": "T", "due_date": "2026-12-01T10:00:00Z", "contact_id": missing_id},
        )
    ).status_code == 404
    assert (
        await client.patch(f"/api/v1/tasks/{missing_id}", headers=headers, json={"status": "completed"})
    ).status_code == 404
    assert len((await client.get("/api/v1/tasks", headers=headers)).json()) == 0

    # BYOK missing delete 404 & invalid short key 422
    assert (
        await client.delete(f"/api/v1/settings/llm-credentials/{missing_id}", headers=headers)
    ).status_code == 404
    assert (
        await client.post(
            "/api/v1/settings/llm-credentials",
            headers=headers,
            json={"provider": "openai", "raw_api_key": "short       "},
        )
    ).status_code == 422


async def test_ai_service_json_validation_stub_variants_and_corrupted_byok(
    test_session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(AIProviderError, match="empty response"):
        parse_llm_analysis_json("   ")

    with pytest.raises(AIProviderError, match="schema validation"):
        parse_llm_analysis_json("{not valid json")

    auth = await register_and_login(client, slug="corrupt-byok", email="admin@corrupt.io")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    tenant_id = uuid.UUID(auth["user"]["tenant_id"])

    # Test claude & openai stub variants directly
    claude_stub = await MultiModelRouter._call_provider_STUB("claude", "s", "u", 0.1)
    assert "claude-3-5-sonnet-stub" in claude_stub["model_name"]
    openai_stub = await MultiModelRouter._call_provider_STUB("openai", "s", "u", 0.1)
    assert "gpt-4o-stub" in openai_stub["model_name"]

    # Save BYOK key, corrupt ciphertext in DB, verify warning + fallback to global_env
    await client.post(
        "/api/v1/settings/llm-credentials",
        headers=headers,
        json={"provider": "openai", "raw_api_key": "sk-proj-original-valid-1234"},
    )
    async with test_session_factory() as session:
        cred = await session.scalar(
            select(TenantLLMCredential).where(TenantLLMCredential.tenant_id == tenant_id)
        )
        assert cred is not None
        cred.encrypted_api_key = b"corrupted_ciphertext_bytes_longer_than_28"
        await session.commit()

        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-global-fallback-9999")
        resolved_key, source = await MultiModelRouter.resolve_provider_key("openai", tenant_id, session)
        assert resolved_key == "sk-global-fallback-9999"
        assert source == "global_env"

    # Mock litellm directly for _call_litellm branch coverage
    async def mock_acompletion(**kwargs):
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content='{"ok": true}'))],
            usage=types.SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )

    monkeypatch.setattr(litellm, "acompletion", mock_acompletion)
    res = await MultiModelRouter.invoke_chat_completion(
        system_prompt="sys",
        user_message="usr",
        preferred_provider="openai",
        tenant_id=None,
        db=None,
    )
    assert res["key_source"] == "global_env"
    assert res["provider"] == "openai"


async def test_mcp_error_paths_and_timeline_and_memory_rate_limit_fallback(
    client: AsyncClient,
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    auth = await register_and_login(client, slug="mcp-edge", email="admin@mcpedge.io")
    headers = {"Authorization": f"Bearer {auth['access_token']}"}
    tenant_id = uuid.UUID(auth["user"]["tenant_id"])
    user_id = uuid.UUID(auth["user"]["id"])

    contact = (
        await client.post(
            "/api/v1/contacts",
            headers=headers,
            json={"first_name": "Hugo", "last_name": "Paz", "email": "hugo@paz.io"},
        )
    ).json()

    async with tenant_session_scope(tenant_id) as session:
        unknown = await MCPAgentExecutionEngine.dispatch_tool(
            "nonexistent_tool", {}, tenant_id, user_id, session
        )
        assert unknown["status"] == "error"

        bad_search = await MCPAgentExecutionEngine.dispatch_tool(
            "crm_search_contacts", {"query": ""}, tenant_id, user_id, session
        )
        assert bad_search["status"] == "error"

        bad_timeline = await MCPAgentExecutionEngine.dispatch_tool(
            "crm_get_interaction_timeline", {"contact_id": "bad-uuid"}, tenant_id, user_id, session
        )
        assert bad_timeline["status"] == "error"

        ok_timeline = await MCPAgentExecutionEngine.dispatch_tool(
            "crm_get_interaction_timeline", {"contact_id": contact["id"]}, tenant_id, user_id, session
        )
        assert ok_timeline["status"] == "success"

        bad_stage = await MCPAgentExecutionEngine.dispatch_tool(
            "crm_update_deal_stage", {"deal_id": "bad-uuid"}, tenant_id, user_id, session
        )
        assert bad_stage["status"] == "error"

        bad_task = await MCPAgentExecutionEngine.dispatch_tool(
            "crm_create_task", {"title": "X", "due_date_iso": "not-iso"}, tenant_id, user_id, session
        )
        assert bad_task["status"] == "error"

    # Force memory rate-limit fallback when Redis client is None
    set_redis_client(None)
    monkeypatch_orig = settings.REDIS_URL
    settings.REDIS_URL = ""
    try:
        me = await client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 200
    finally:
        settings.REDIS_URL = monkeypatch_orig
