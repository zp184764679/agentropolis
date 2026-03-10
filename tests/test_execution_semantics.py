"""Execution semantics, job queue, retry, and backfill tests."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import agentropolis.services.recovery_svc as recovery_svc
from agentropolis.config import settings
from agentropolis.database import get_session
from agentropolis.main import app
from agentropolis.models import Base, GameState
from agentropolis.services.execution_svc import run_due_execution_jobs
from agentropolis.services.game_engine import run_housekeeping_iteration
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world


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

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client, session_factory
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


def _admin_headers(token: str = "root-token") -> dict[str, str]:
    return {"X-Control-Plane-Token": token}


def test_execution_endpoint_accepts_and_processes_backfill_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONTROL_PLANE_ADMIN_TOKEN", "root-token")

    async def scenario() -> None:
        async with _seeded_client() as (client, session_factory):
            async with session_factory() as session:
                state = await session.get(GameState, 1)
                assert state is not None
                state.current_tick = 5
                state.last_tick_at = datetime.now(UTC) - timedelta(
                    seconds=max(int(state.tick_interval_seconds), 1)
                )
                await session.commit()

            response = await client.post(
                "/meta/execution/jobs/housekeeping-backfill",
                headers=_admin_headers(),
                json={
                    "requested_tick": 6,
                    "reason_code": "manual_backfill",
                    "note": "repair housekeeping gap",
                },
            )
            assert response.status_code == 202
            accepted = response.json()
            assert accepted["status"] == "accepted"
            assert accepted["job_type"] == "housekeeping_backfill"

            listed = await client.get("/meta/execution/jobs", headers=_admin_headers())
            assert listed.status_code == 200
            assert any(job["job_id"] == accepted["job_id"] for job in listed.json()["jobs"])

            await run_due_execution_jobs(
                now=datetime.now(UTC),
                limit=4,
                session_factory=session_factory,
            )

            snapshot = await client.get("/meta/execution")
            assert snapshot.status_code == 200
            payload = snapshot.json()
            assert payload["counts"]["by_status"]["completed"] >= 1
            latest = payload["housekeeping_phase_contract"]["latest_sweep"]
            assert latest is not None
            assert latest["trigger_kind"] == "backfill"
            assert latest["execution_job_id"] == accepted["job_id"]
            assert latest["phase_results"]["production"]["status"] == "completed"

    asyncio.run(scenario())


def test_housekeeping_iteration_auto_backfills_missed_sweeps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "EXECUTION_MAX_BACKFILL_SWEEPS", 4)

    async def scenario() -> None:
        async with _seeded_client() as (_client, session_factory):
            now = datetime.now(UTC)
            async with session_factory() as session:
                state = await session.get(GameState, 1)
                assert state is not None
                state.current_tick = 2
                state.last_tick_at = now - timedelta(seconds=int(state.tick_interval_seconds) * 2)
                await session.commit()

            summary = await run_housekeeping_iteration(now=now, session_factory=session_factory)
            assert summary["backfill"]["missed_sweeps"] >= 2
            assert summary["backfill"]["enqueued"] >= 1
            assert summary["execution_jobs"]["processed"] >= 1

            async with session_factory() as session:
                state = await session.get(GameState, 1)
                assert state is not None
                assert int(state.current_tick) >= 3

    asyncio.run(scenario())


def test_execution_jobs_dead_letter_and_can_be_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONTROL_PLANE_ADMIN_TOKEN", "root-token")
    monkeypatch.setattr(settings, "EXECUTION_JOB_RETRY_DELAY_SECONDS", 0)

    async def _boom(_session):
        raise RuntimeError("forced repair failure")

    monkeypatch.setattr(recovery_svc, "repair_derived_state", _boom)

    async def scenario() -> None:
        async with _seeded_client() as (client, session_factory):
            response = await client.post(
                "/meta/execution/jobs/repair-derived-state",
                headers=_admin_headers(),
                json={"reason_code": "repair", "note": "force dead letter"},
            )
            assert response.status_code == 202
            job_id = response.json()["job_id"]

            for _ in range(int(settings.EXECUTION_JOB_MAX_ATTEMPTS)):
                await run_due_execution_jobs(
                    now=datetime.now(UTC),
                    limit=1,
                    session_factory=session_factory,
                )

            listed = await client.get("/meta/execution/jobs", headers=_admin_headers())
            assert listed.status_code == 200
            dead_letter = next(job for job in listed.json()["jobs"] if job["job_id"] == job_id)
            assert dead_letter["status"] == "dead_letter"
            assert dead_letter["dead_letter_reason"] == "forced repair failure"

            retry = await client.post(
                f"/meta/execution/jobs/{job_id}/retry",
                headers=_admin_headers(),
                json={"reason_code": "retry", "note": "manual retry"},
            )
            assert retry.status_code == 202
            assert retry.json()["status"] == "accepted"

    asyncio.run(scenario())
