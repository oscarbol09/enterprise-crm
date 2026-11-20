"""
Integration Tests for Authentication, Refresh Token Rotation, Reuse Detection, and Rate Limiting.
"""

import uuid

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from src.core.config import settings
from src.models.entities import User

from tests.conftest import register_and_login


async def test_register_login_me_and_duplicate_slug(client: AsyncClient) -> None:
    data = await register_and_login(client, slug="alpha-inc", email="ceo@alpha.io", name="Ana Pérez")
    access_token = data["access_token"]
    assert data["user"]["role"] == "admin"
    assert data["user"]["tenant_slug"] == "alpha-inc"
    assert "crm_refresh_token" in client.cookies

    dup = await client.post(
        "/api/v1/auth/register",
        json={
            "tenant_name": "Alpha Clone",
            "tenant_slug": "alpha-inc",
            "admin_full_name": "Clone",
            "admin_email": "clone@alpha.io",
            "password": "StrongPassword123!",
        },
    )
    assert dup.status_code == 409

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me.status_code == 200
    assert me.json()["tenant_slug"] == "alpha-inc"

    bad_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "ceo@alpha.io", "password": "WrongPassword", "tenant_slug": "alpha-inc"},
    )
    assert bad_login.status_code == 401


async def test_ambiguous_email_across_tenants_requires_slug(client: AsyncClient) -> None:
    await register_and_login(client, slug="org-one", email="shared@corp.io")
    await register_and_login(client, slug="org-two", email="shared@corp.io")

    ambiguous = await client.post(
        "/api/v1/auth/login",
        json={"email": "shared@corp.io", "password": "StrongPass123!"},
    )
    assert ambiguous.status_code == 409

    scoped = await client.post(
        "/api/v1/auth/login",
        json={"email": "shared@corp.io", "password": "StrongPass123!", "tenant_slug": "org-two"},
    )
    assert scoped.status_code == 200
    assert scoped.json()["user"]["tenant_slug"] == "org-two"


async def test_refresh_rotation_and_reuse_detection_revokes_family(client: AsyncClient) -> None:
    reg = await register_and_login(client, slug="beta-crm", email="admin@beta.io")
    refresh_1 = reg["refresh_token"]

    rot = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_1})
    assert rot.status_code == 200
    refresh_2 = rot.json()["refresh_token"]
    assert refresh_2 != refresh_1

    # Replay stolen/old token refresh_1 -> triggers reuse detection and revokes whole family
    replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_1})
    assert replay.status_code == 401
    assert "reuse detected" in replay.json()["detail"].lower()

    # Legitimate token refresh_2 in the same family must also now be rejected
    post_revocation = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_2})
    assert post_revocation.status_code == 401


async def test_logout_revokes_session_and_inactive_user_blocked(
    client: AsyncClient,
    test_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    reg = await register_and_login(client, slug="gamma-crm", email="admin@gamma.io")
    access_token = reg["access_token"]
    refresh_token = reg["refresh_token"]
    user_id = uuid.UUID(reg["user"]["id"])

    logout_resp = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert logout_resp.status_code == 204

    after_logout = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert after_logout.status_code == 401

    # Deactivate user in DB and verify existing non-expired JWT is rejected by get_tenant_db
    async with test_session_factory() as session:
        await session.execute(update(User).where(User.id == user_id).values(is_active=False))
        await session.commit()

    deactivated = await client.get("/api/v1/contacts", headers={"Authorization": f"Bearer {access_token}"})
    assert deactivated.status_code == 401


async def test_login_rate_limiting_returns_429_with_retry_after(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    await register_and_login(client, slug="rl-corp", email="admin@rl.io")

    last_status = 0
    last_headers = {}
    for _ in range(25):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@rl.io", "password": "wrong", "tenant_slug": "rl-corp"},
        )
        last_status = resp.status_code
        last_headers = dict(resp.headers)
        if last_status == 429:
            break

    assert last_status == 429
    assert "retry-after" in {k.lower() for k in last_headers}
