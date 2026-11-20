"""
Shared Pytest Fixtures: Hermetic Async SQLite Engine, FakeRedis, and Multi-Tenant Test Helpers.
"""

import os
import uuid
from collections.abc import AsyncGenerator

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Force deterministic test environment defaults before importing app settings
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ALLOW_OFFLINE_AI_STUB", "true")
os.environ.setdefault("RATE_LIMIT_ENABLED", "true")

from src.core import database as db_module  # noqa: E402
from src.core.config import settings  # noqa: E402
from src.core.database import Base  # noqa: E402
from src.core.rate_limit import reset_memory_rate_limits, set_redis_client  # noqa: E402
from src.core.security import get_password_hash  # noqa: E402
from src.main import app  # noqa: E402
from src.models.entities import Tenant, User  # noqa: E402
from src.services.pipeline_service import ensure_default_pipeline  # noqa: E402


@pytest.fixture(autouse=True)
def isolate_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guarantees tests never pick up host environment LLM API keys."""
    for key in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
        monkeypatch.setattr(settings, key, None)


@pytest.fixture
async def test_session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    orig_engine = db_module.engine
    orig_factory = db_module.AsyncSessionLocal
    db_module.engine = test_engine
    db_module.AsyncSessionLocal = factory

    # Ensure dependencies & services importing AsyncSessionLocal directly also point to test factory
    from src.core import dependencies as deps_module

    deps_module.AsyncSessionLocal = factory

    try:
        yield factory
    finally:
        db_module.engine = orig_engine
        db_module.AsyncSessionLocal = orig_factory
        deps_module.AsyncSessionLocal = orig_factory
        await test_engine.dispose()


@pytest.fixture(autouse=True)
async def fake_redis() -> AsyncGenerator[fakeredis.aioredis.FakeRedis, None]:
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    set_redis_client(client)
    reset_memory_rate_limits()
    try:
        yield client
    finally:
        await client.aclose()
        set_redis_client(None)
        reset_memory_rate_limits()


@pytest.fixture
async def client(test_session_factory: async_sessionmaker[AsyncSession]) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def register_and_login(
    client: AsyncClient,
    slug: str,
    email: str,
    password: str = "StrongPass123!",
    name: str = "Admin User",
) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "tenant_name": f"Workspace {slug}",
            "tenant_slug": slug,
            "admin_full_name": name,
            "admin_email": email,
            "password": password,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def create_role_user_and_login(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    tenant_slug: str,
    email: str,
    role: str,
    password: str = "RolePass123!",
) -> dict:
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            email=email,
            password_hash=get_password_hash(password),
            full_name=f"{role.title()} Tester",
            role=role,
            is_active=True,
        )
        session.add(user)
        await session.commit()

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "tenant_slug": tenant_slug},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def seed_raw_tenant(
    session_factory: async_sessionmaker[AsyncSession], slug: str
) -> tuple[Tenant, User]:
    async with session_factory() as session:
        tenant = Tenant(id=uuid.uuid4(), name=slug, slug=slug, is_active=True)
        session.add(tenant)
        await session.flush()
        user = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email=f"owner@{slug}.io",
            password_hash=get_password_hash("SeedPass123!"),
            full_name="Owner",
            role="admin",
            is_active=True,
        )
        session.add(user)
        await ensure_default_pipeline(session, tenant.id)
        await session.commit()
        return tenant, user
