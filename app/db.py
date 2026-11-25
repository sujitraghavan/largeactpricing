"""Database engine and session management for the Commercial Auto Loss Rating Engine."""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# Async SQLAlchemy engine bound to the Supabase PostgreSQL database.
async_engine: AsyncEngine = create_async_engine(
    settings.supabase_db_url,
    echo=True,
    pool_pre_ping=True,
)


async_session_factory = async_sessionmaker(
    async_engine,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session."""
    async with async_session_factory() as session:
        yield session
