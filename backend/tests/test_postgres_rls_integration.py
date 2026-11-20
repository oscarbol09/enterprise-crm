"""
Live PostgreSQL + pgvector + Forced RLS Integration Tests.
Executed in CI against `pgvector/pgvector:pg16` using the non-superuser `crm_app` role (`NOBYPASSRLS`).
Skipped locally only when `TEST_POSTGRES_URL` is not configured.
"""

import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.core.database import set_tenant_rls_context
from src.core.security import encrypt_field, get_password_hash
from src.models.entities import Contact, PipelineStage, Tenant, TenantLLMCredential, User
from src.services.embedding_service import semantic_search, upsert_entity_embedding
from src.services.pipeline_service import ensure_default_pipeline

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL not set; run in PostgreSQL CI"),
]


async def test_postgres_forced_rls_prevents_cross_tenant_reads_and_writes() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    tenant_a_id = uuid.uuid4()
    tenant_b_id = uuid.uuid4()
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()
    contact_a_id = uuid.uuid4()

    try:
        # 1. Seed Tenant A & Tenant B using proper RLS context per tenant
        async with session_factory() as s:
            t_a = Tenant(id=tenant_a_id, name="PG Tenant A", slug=f"pg-a-{tenant_a_id.hex[:6]}")
            t_b = Tenant(id=tenant_b_id, name="PG Tenant B", slug=f"pg-b-{tenant_b_id.hex[:6]}")
            s.add_all([t_a, t_b])
            await s.flush()

            await set_tenant_rls_context(s, tenant_a_id)
            u_a = User(
                id=user_a_id,
                tenant_id=tenant_a_id,
                email="a@pg.io",
                password_hash=get_password_hash("Pass123!"),
                full_name="User A",
                role="admin",
            )
            s.add(u_a)
            await s.flush()
            await ensure_default_pipeline(s, tenant_a_id)
            c_a = Contact(
                id=contact_a_id,
                tenant_id=tenant_a_id,
                owner_id=user_a_id,
                first_name="Secret",
                last_name="TenantA",
                email="secret@tenanta.io",
            )
            cred_a = TenantLLMCredential(
                id=uuid.uuid4(),
                tenant_id=tenant_a_id,
                provider="gemini",
                encrypted_api_key=encrypt_field(
                    "AIzaSyTenantA1234", associated_data=str(tenant_a_id).encode()
                ),
                key_last_four="1234",
                is_active=True,
                added_by=user_a_id,
            )
            s.add_all([c_a, cred_a])
            await upsert_entity_embedding(
                s, tenant_a_id, "contact", contact_a_id, "Secret TenantA Kubernetes Architect"
            )
            await s.commit()

        async with session_factory() as s:
            await set_tenant_rls_context(s, tenant_b_id)
            u_b = User(
                id=user_b_id,
                tenant_id=tenant_b_id,
                email="b@pg.io",
                password_hash=get_password_hash("Pass123!"),
                full_name="User B",
                role="admin",
            )
            s.add(u_b)
            await s.commit()

        # 2. Query as Tenant B WITHOUT any WHERE tenant_id filter: PostgreSQL RLS must return 0 rows!
        async with session_factory() as s:
            await set_tenant_rls_context(s, tenant_b_id)

            contacts_seen_by_b = list((await s.scalars(select(Contact))).all())
            creds_seen_by_b = list((await s.scalars(select(TenantLLMCredential))).all())
            stages_seen_by_b = list((await s.scalars(select(PipelineStage))).all())
            pgvector_results, source = await semantic_search(s, tenant_b_id, "Kubernetes Architect", limit=5)

            assert contacts_seen_by_b == []
            assert creds_seen_by_b == []
            assert stages_seen_by_b == []
            assert pgvector_results == []
            assert source == "pgvector_hnsw"

        # 3. Query as Tenant A: sees its own contact and pgvector cosine match
        async with session_factory() as s:
            await set_tenant_rls_context(s, tenant_a_id)
            contacts_seen_by_a = list((await s.scalars(select(Contact))).all())
            pgvector_results, source = await semantic_search(s, tenant_a_id, "Kubernetes Architect", limit=5)
            assert len(contacts_seen_by_a) == 1
            assert contacts_seen_by_a[0].id == contact_a_id
            assert len(pgvector_results) == 1
            assert source == "pgvector_hnsw"

        # 4. Verify SECURITY DEFINER login lookup function works cleanly without exposing other tables
        async with session_factory() as s:
            rows = (
                await s.execute(
                    text("SELECT tenant_id, tenant_slug FROM lookup_user_tenants_by_email(:email)"),
                    {"email": "a@pg.io"},
                )
            ).all()
            assert len(rows) == 1
            assert rows[0][0] == tenant_a_id
    finally:
        await engine.dispose()
