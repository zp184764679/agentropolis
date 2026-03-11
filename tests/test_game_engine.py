"""Housekeeping status, control, and timeout regression coverage."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from click.testing import CliRunner
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import agentropolis.services.game_engine as game_engine
from agentropolis.config import settings
from agentropolis.database import get_session
from agentropolis.main import app
from agentropolis.models import Base, GameState
from agentropolis.runtime_meta import build_runtime_metadata
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world
from agentropolis.cli import cli


@asynccontextmanager
async def _seeded_client():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        await seed_game_data(session)
        await seed_world(session)
        await session.commit()

    game_engine._set_last_sweep_summary(None)
    app.dependency_overrides[get_session] = override_get_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client, session_factory
    finally:
        game_engine._set_last_sweep_summary(None)
        app.dependency_overrides.clear()
        await engine.dispose()


def test_run_housekeeping_sweep_updates_runtime_state_and_summary() -> None:
    async def scenario() -> None:
        async with _seeded_client() as (_client, session_factory):
            now = datetime.now(UTC)
            async with session_factory() as session:
                summary = await game_engine.run_housekeeping_sweep(
                    session,
                    now=now,
                    tick_number=7,
                )
                await session.commit()
                state = await session.get(GameState, 1)
                assert state is not None
                assert state.current_tick == 7
                assert state.last_housekeeping_at is not None
                assert state.last_housekeeping_at.replace(tzinfo=UTC) == now
                assert summary["log_id"] > 0
                assert "trade" in summary

            cached = game_engine.get_last_housekeeping_summary()
            assert cached is not None
            assert cached["current_tick"] == 7
            assert cached["completed_at"] == now.isoformat()

    asyncio.run(scenario())


def test_housekeeping_status_history_and_health_endpoints() -> None:
    async def scenario() -> None:
        async with _seeded_client() as (client, session_factory):
            now = datetime.now(UTC)
            async with session_factory() as session:
                await game_engine.run_housekeeping_sweep(session, now=now, tick_number=3)
                await session.commit()

            status_response = await client.get("/api/game/housekeeping/status")
            assert status_response.status_code == 200
            status_payload = status_response.json()
            assert status_payload["housekeeping_enabled"] is True
            assert status_payload["last_sweep"]["sweep_count"] == 3
            assert status_payload["last_housekeeping_at"] == now.isoformat()

            history_response = await client.get("/api/game/housekeeping/history", params={"limit": 1})
            assert history_response.status_code == 200
            history_payload = history_response.json()
            assert history_payload["total"] >= 1
            assert history_payload["entries"][0]["sweep_count"] == 3

            health_response = await client.get("/health")
            assert health_response.status_code == 200
            assert health_response.json()["last_housekeeping_at"] == now.isoformat()

    asyncio.run(scenario())


def test_run_housekeeping_iteration_respects_disabled_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        async with _seeded_client() as (_client, session_factory):
            monkeypatch.setattr(settings, "HOUSEKEEPING_ENABLED", False)
            summary = await game_engine.run_housekeeping_iteration(session_factory=session_factory)
            assert summary["disabled"] is True
            assert summary["reason"] == "housekeeping_disabled"

    asyncio.run(scenario())


def test_housekeeping_phase_timeout_records_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow_consumption(_session):
        await asyncio.sleep(1.1)
        return {"companies_processed": 0}

    async def scenario() -> None:
        async with _seeded_client() as (_client, session_factory):
            monkeypatch.setattr(settings, "HOUSEKEEPING_PHASE_TIMEOUT", 1)
            monkeypatch.setattr(settings, "EXECUTION_PHASE_MAX_ATTEMPTS", 1)
            monkeypatch.setattr(game_engine, "tick_consumption", slow_consumption)

            async with session_factory() as session:
                summary = await game_engine.run_housekeeping_sweep(
                    session,
                    now=datetime.now(UTC),
                    tick_number=9,
                )
                await session.commit()

            assert summary["error_count"] >= 1
            assert summary["phase_results"]["consumption"]["status"] == "failed"
            assert "timed out" in summary["phase_results"]["consumption"]["last_error"]["detail"]

    asyncio.run(scenario())


def test_cli_sweep_dry_run_rolls_back_state(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> async_sessionmaker[AsyncSession]:
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            await seed_game_data(session)
            await seed_world(session)
            await session.commit()
        return session_factory

    session_factory = asyncio.run(scenario())
    monkeypatch.setattr(game_engine, "async_session", session_factory)
    game_engine._set_last_sweep_summary(None)

    runner = CliRunner()
    result = runner.invoke(cli, ["sweep", "--dry-run"])
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output.lower()

    async def verify() -> None:
        async with session_factory() as session:
            state = await session.get(GameState, 1)
            assert state is not None
            assert state.current_tick == 0
            assert state.last_housekeeping_at is None

    asyncio.run(verify())
    game_engine._set_last_sweep_summary(None)


def test_runtime_metadata_reports_housekeeping_surface() -> None:
    meta = build_runtime_metadata()
    assert meta["housekeeping_surface"]["status_endpoint"] == "/api/game/housekeeping/status"
    assert meta["housekeeping_surface"]["history_endpoint"] == "/api/game/housekeeping/history"
    assert meta["housekeeping_surface"]["manual_cli"] == "agentropolis sweep"
    assert meta["housekeeping_surface"]["last_housekeeping_at_source"] == "game_state.last_housekeeping_at"
