"""
Database Engine & Session Management with PostgreSQL Forced RLS Context Binding.
"""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.core.config import settings


def _build_engine(database_url: str) -> AsyncEngine:
    is_sqlite = database_url.startswith("sqlite")
    if is_sqlite:
        return create_async_engine(database_url, echo=False)
    return create_async_engine(
        database_url,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=False,
    )


engine: AsyncEngine = _build_engine(settings.DATABASE_URL)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def set_tenant_rls_context(session: AsyncSession, tenant_id: uuid.UUID | str) -> None:
    """
    Binds the tenant UUID to PostgreSQL transaction-local GUC `app.current_tenant_id`
    via `set_config(..., true)` (parameterized protocol compatible with asyncpg).
    """
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )


async def get_raw_db() -> AsyncGenerator[AsyncSession, None]:
    """Provides a session without tenant binding (only for pre-auth tenant lookup/registration)."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def tenant_session_scope(tenant_id: uuid.UUID | str) -> AsyncGenerator[AsyncSession, None]:
    """
    Short-lived transactional session bound to a single tenant for background tasks,
    MCP tool invocations, or zero-I/O segmented read/write blocks.
    """
    async with AsyncSessionLocal() as session:
        try:
            await set_tenant_rls_context(session, tenant_id)
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
