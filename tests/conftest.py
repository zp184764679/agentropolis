"""Shared test fixtures for Agentropolis tests.

Provides:
- In-memory SQLite async engine for fast tests
- Auto-created tables per test session
- Database session fixture
- Pre-seeded game data fixture
- Test company factory
"""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agentropolis.models import Base


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def engine():
    """Create async engine with SQLite for tests."""
    eng = create_async_engine("sqlite+aiosqlite:///", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine) -> AsyncSession:
    """Fresh database session for each test, rolled back after."""
    async_sess = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_sess() as sess:
        async with sess.begin():
            yield sess
            await sess.rollback()


@pytest.fixture
async def seeded_session(session: AsyncSession) -> AsyncSession:
    """Session with game seed data loaded."""
    from agentropolis.services.seed import seed_game_data
    await seed_game_data(session)
    return session
