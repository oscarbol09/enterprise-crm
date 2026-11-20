"""
Idempotent Development Seed Script.
Run via: `python -m src.core.seed`
"""

import asyncio
import uuid
from datetime import date, timedelta
from decimal import Decimal

import structlog
from sqlalchemy import select

from src.core.database import AsyncSessionLocal, set_tenant_rls_context
from src.core.security import get_password_hash_async
from src.models.entities import Account, Contact, Deal, Interaction, Tenant, User
from src.services.embedding_service import upsert_entity_embedding
from src.services.pipeline_service import ensure_default_pipeline

logger = structlog.get_logger(__name__)

DEMO_SLUG = "acme-corp"
DEMO_ADMIN_EMAIL = "admin@acme.io"
DEMO_ADMIN_PASS = "DemoAdmin123!"  # noqa: S105
DEMO_REP_EMAIL = "rep@acme.io"
DEMO_REP_PASS = "DemoRep123!"  # noqa: S105


async def seed_demo_workspace() -> None:
    async with AsyncSessionLocal() as session:
        existing = await session.scalar(select(Tenant).where(Tenant.slug == DEMO_SLUG))
        if existing:
            logger.info("Demo workspace already exists", tenant_slug=DEMO_SLUG)
            return

        tenant = Tenant(
            id=uuid.uuid4(),
            name="Acme Enterprise Corp",
            slug=DEMO_SLUG,
            plan_tier="enterprise",
            is_active=True,
        )
        session.add(tenant)
        await session.flush()

        await set_tenant_rls_context(session, tenant.id)

        admin = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email=DEMO_ADMIN_EMAIL,
            password_hash=await get_password_hash_async(DEMO_ADMIN_PASS),
            full_name="Elena Mendoza",
            role="admin",
            is_active=True,
        )
        rep = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email=DEMO_REP_EMAIL,
            password_hash=await get_password_hash_async(DEMO_REP_PASS),
            full_name="Carlos Navarro",
            role="sales_rep",
            is_active=True,
        )
        session.add_all([admin, rep])
        await session.flush()

        stages = await ensure_default_pipeline(session, tenant.id)
        stage_by_pos = {s.position: s for s in stages}

        account = Account(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            name="Nordic Cloud Systems",
            industry="Cloud Infrastructure",
            website="https://nordiccloud.example.com",
            annual_revenue=Decimal("18500000.00"),
            employee_count=420,
            owner_id=admin.id,
        )
        session.add(account)
        await session.flush()

        contact_1 = Contact(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            account_id=account.id,
            owner_id=rep.id,
            first_name="Laura",
            last_name="Serrano",
            email="laura.serrano@nordiccloud.example.com",
            phone="+34 611 223 344",
            job_title="VP of Engineering",
            lead_score=Decimal("88.50"),
            lifecycle_stage="sales_qualified",
        )
        contact_2 = Contact(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            account_id=account.id,
            owner_id=rep.id,
            first_name="Mateo",
            last_name="Vargas",
            email="mateo.vargas@fintech-andina.example.com",
            phone="+57 300 555 0199",
            job_title="Head of RevOps",
            lead_score=Decimal("74.00"),
            lifecycle_stage="marketing_qualified",
        )
        session.add_all([contact_1, contact_2])
        await session.flush()

        await upsert_entity_embedding(
            session,
            tenant.id,
            "contact",
            contact_1.id,
            "Laura Serrano VP Engineering Nordic Cloud Systems Kubernetes SaaS migration",
        )
        await upsert_entity_embedding(
            session,
            tenant.id,
            "contact",
            contact_2.id,
            "Mateo Vargas Head of RevOps Fintech pipeline forecasting automation",
        )

        deal_1 = Deal(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            pipeline_id=stages[0].pipeline_id,
            stage_id=stage_by_pos[3].id,
            account_id=account.id,
            contact_id=contact_1.id,
            owner_id=rep.id,
            title="Migración Multi-Región CRM (5,000 asientos)",
            amount=Decimal("145000.00"),
            currency="USD",
            expected_close_date=date.today() + timedelta(days=21),
            forecast_category="best_case",
            win_probability=stage_by_pos[3].default_probability,
        )
        deal_2 = Deal(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            pipeline_id=stages[0].pipeline_id,
            stage_id=stage_by_pos[2].id,
            contact_id=contact_2.id,
            owner_id=rep.id,
            title="Licenciamiento Copilot IA + Bóveda BYOK",
            amount=Decimal("48000.00"),
            currency="USD",
            expected_close_date=date.today() + timedelta(days=45),
            forecast_category="pipeline",
            win_probability=stage_by_pos[2].default_probability,
        )
        session.add_all([deal_1, deal_2])
        await session.flush()

        session.add(
            Interaction(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                user_id=rep.id,
                contact_id=contact_1.id,
                deal_id=deal_1.id,
                type="meeting",
                direction="outbound",
                subject="Revisión técnica de aislamiento RLS y BYOK",
                content_body="El equipo de seguridad validó AES-256-GCM y pidió propuesta de SLA antes del viernes.",
            )
        )

        await session.commit()
        logger.info(
            "Seeded demo workspace successfully",
            tenant_slug=DEMO_SLUG,
            admin_email=DEMO_ADMIN_EMAIL,
        )


if __name__ == "__main__":
    asyncio.run(seed_demo_workspace())
