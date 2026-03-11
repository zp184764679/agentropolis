"""Concurrency guard tests for authenticated traffic and write serialization."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import agentropolis.api.agent as agent_api
from agentropolis.config import settings
from agentropolis.database import get_session
from agentropolis.main import app
from agentropolis.middleware import REQUEST_ID_HEADER
from agentropolis.models import Base
from agentropolis.services.concurrency import (
    ERROR_CODE_HEADER,
    acquire_entity_locks,
    acquire_housekeeping_slot,
    acquire_request_slot,
    get_concurrency_snapshot,
)
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world


def _assert_error_contract(
    response,
    *,
    status_code: int,
    error_code: str,
) -> None:
    body = response.json()
    assert response.status_code == status_code
    assert body["error_code"] == error_code
    assert response.headers[ERROR_CODE_HEADER] == error_code
    assert response.headers[REQUEST_ID_HEADER]
    assert body["request_id"] == response.headers[REQUEST_ID_HEADER]


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


def _api_headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


async def _register_agent_and_company(
    client: AsyncClient,
    *,
    agent_name: str,
    company_name: str,
) -> tuple[str, str]:
    agent_response = await client.post("/api/agent/register", json={"name": agent_name})
    assert agent_response.status_code == 200
    agent_key = agent_response.json()["api_key"]

    company_response = await client.post(
        "/api/agent/company",
        headers=_api_headers(agent_key),
        json={"company_name": company_name},
    )
    assert company_response.status_code == 200
    return agent_key, agent_key


def test_request_slots_preserve_housekeeping_capacity_and_timeout_when_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONCURRENCY_MAX_CONCURRENT", 2)
    monkeypatch.setattr(settings, "HOUSEKEEPING_RESERVED_SLOTS", 1)
    monkeypatch.setattr(settings, "CONCURRENCY_SLOT_TIMEOUT", 0.01)

    async def scenario() -> None:
        async with acquire_request_slot():
            with pytest.raises(HTTPException) as excinfo:
                async with acquire_request_slot():
                    pytest.fail("second request slot should time out")

            assert excinfo.value.status_code == 503
            assert excinfo.value.headers[ERROR_CODE_HEADER] == "concurrency_slot_timeout"

            async with acquire_housekeeping_slot():
                snapshot = get_concurrency_snapshot()
                assert snapshot["request_slots"]["in_use"] == 1
                assert snapshot["housekeeping_slots"]["in_use"] == 1

        snapshot = get_concurrency_snapshot()
        assert snapshot["recent_failures"]["slot_timeouts"] == 1
        assert snapshot["request_slots"]["in_use"] == 0
        assert snapshot["housekeeping_slots"]["in_use"] == 0

    asyncio.run(scenario())


def test_entity_locks_sort_keys_and_timeout_on_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONCURRENCY_LOCK_TIMEOUT", 0.01)
    monkeypatch.setattr(settings, "CONCURRENCY_STRIPE_COUNT", 64)

    async def scenario() -> None:
        async with acquire_entity_locks(["guild:9", "agent:2", "agent:2"]) as info:
            assert info["lock_keys"] == ["agent:2", "guild:9"]
            assert info["stripe_indices"] == sorted(info["stripe_indices"])

            with pytest.raises(HTTPException) as excinfo:
                async with acquire_entity_locks(["agent:2"]):
                    pytest.fail("conflicting entity lock should time out")

            assert excinfo.value.status_code == 429
            assert excinfo.value.headers[ERROR_CODE_HEADER] == (
                "concurrency_entity_lock_timeout"
            )

        snapshot = get_concurrency_snapshot()
        assert snapshot["recent_failures"]["entity_lock_timeouts"] == 1

    asyncio.run(scenario())


def test_rate_limits_apply_per_authenticated_actor_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONTROL_PLANE_ADMIN_TOKEN", "root-token")
    monkeypatch.setattr(settings, "RATE_LIMIT_AGENT_REQUESTS_PER_WINDOW", 3)
    monkeypatch.setattr(settings, "RATE_LIMIT_COMPANY_REQUESTS_PER_WINDOW", 1)
    monkeypatch.setattr(settings, "RATE_LIMIT_ADMIN_REQUESTS_PER_WINDOW", 1)

    async def scenario() -> None:
        async with _seeded_client() as (client, _session_factory):
            agent_key, company_key = await _register_agent_and_company(
                client,
                agent_name="Throttle Agent",
                company_name="Throttle Works",
            )

            first_agent = await client.get("/api/agent/status", headers=_api_headers(agent_key))
            second_agent = await client.get("/api/agent/status", headers=_api_headers(agent_key))
            third_agent = await client.get("/api/agent/status", headers=_api_headers(agent_key))

            assert first_agent.status_code == 200
            assert second_agent.status_code == 200
            _assert_error_contract(
                third_agent,
                status_code=429,
                error_code="concurrency_rate_limited",
            )

            first_company = await client.get("/api/inventory", headers=_api_headers(company_key))
            second_company = await client.get("/api/inventory", headers=_api_headers(company_key))
            assert first_company.status_code == 200
            _assert_error_contract(
                second_company,
                status_code=429,
                error_code="concurrency_rate_limited",
            )

            first_admin = await client.get(
                "/meta/control-plane",
                headers={"X-Control-Plane-Token": "root-token"},
            )
            second_admin = await client.get(
                "/meta/control-plane",
                headers={"X-Control-Plane-Token": "root-token"},
            )
            assert first_admin.status_code == 200
            _assert_error_contract(
                second_admin,
                status_code=429,
                error_code="concurrency_rate_limited",
            )

            snapshot = get_concurrency_snapshot()
            assert snapshot["rate_limits"]["hits"] >= 3

    asyncio.run(scenario())


def test_authenticated_request_slot_timeout_returns_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONCURRENCY_MAX_CONCURRENT", 2)
    monkeypatch.setattr(settings, "HOUSEKEEPING_RESERVED_SLOTS", 1)
    monkeypatch.setattr(settings, "CONCURRENCY_SLOT_TIMEOUT", 0.05)
    monkeypatch.setattr(settings, "RATE_LIMIT_AGENT_REQUESTS_PER_WINDOW", 50)

    original = agent_api.get_agent_status
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_status(session, agent_id):
        started.set()
        await release.wait()
        return await original(session, agent_id)

    monkeypatch.setattr(agent_api, "get_agent_status", slow_status)

    async def scenario() -> None:
        async with _seeded_client() as (client, _session_factory):
            agent_key, _company_key = await _register_agent_and_company(
                client,
                agent_name="Slot Agent",
                company_name="Slot Works",
            )

            first = asyncio.create_task(
                client.get("/api/agent/status", headers=_api_headers(agent_key))
            )
            await started.wait()
            second = await client.get("/api/agent/status", headers=_api_headers(agent_key))
            release.set()
            first_response = await first

            assert first_response.status_code == 200
            _assert_error_contract(
                second,
                status_code=503,
                error_code="concurrency_slot_timeout",
            )

    asyncio.run(scenario())


def test_authenticated_write_lock_timeout_returns_429(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONCURRENCY_MAX_CONCURRENT", 3)
    monkeypatch.setattr(settings, "HOUSEKEEPING_RESERVED_SLOTS", 1)
    monkeypatch.setattr(settings, "CONCURRENCY_LOCK_TIMEOUT", 0.05)
    monkeypatch.setattr(settings, "RATE_LIMIT_AGENT_REQUESTS_PER_WINDOW", 50)

    original = agent_api.rest_agent
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_rest(session, agent_id):
        started.set()
        await release.wait()
        return await original(session, agent_id)

    monkeypatch.setattr(agent_api, "rest_agent", slow_rest)

    async def scenario() -> None:
        async with _seeded_client() as (client, _session_factory):
            agent_key, _company_key = await _register_agent_and_company(
                client,
                agent_name="Lock Agent",
                company_name="Lock Works",
            )

            first = asyncio.create_task(
                client.post("/api/agent/rest", headers=_api_headers(agent_key))
            )
            await started.wait()
            second = await client.post("/api/agent/rest", headers=_api_headers(agent_key))
            release.set()
            first_response = await first

            assert first_response.status_code == 200
            _assert_error_contract(
                second,
                status_code=429,
                error_code="concurrency_entity_lock_timeout",
            )

    asyncio.run(scenario())


def test_concurrency_state_surfaces_through_meta_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONCURRENCY_MAX_CONCURRENT", 2)
    monkeypatch.setattr(settings, "HOUSEKEEPING_RESERVED_SLOTS", 1)
    monkeypatch.setattr(settings, "CONCURRENCY_SLOT_TIMEOUT", 0.01)

    async def scenario() -> None:
        async with acquire_request_slot():
            with pytest.raises(HTTPException):
                async with acquire_request_slot():
                    pytest.fail("second request slot should time out")

        async with _seeded_client() as (client, _session_factory):
            observability = await client.get("/meta/observability")
            readiness = await client.get("/meta/rollout-readiness")
            alerts = await client.get("/meta/alerts")

            assert observability.status_code == 200
            assert readiness.status_code == 200
            assert alerts.status_code == 200

            observability_payload = observability.json()
            readiness_payload = readiness.json()
            alert_payload = alerts.json()

            assert observability_payload["concurrency"]["recent_failures"]["slot_timeouts"] >= 1
            assert (
                observability_payload["concurrency"]["request_slots"]["capacity"]
                == settings.CONCURRENCY_MAX_CONCURRENT - settings.HOUSEKEEPING_RESERVED_SLOTS
            )
            assert readiness_payload["gates"]["concurrency_guard"]["ready"] is True
            codes = {entry["code"] for entry in alert_payload["alerts"]}
            assert "concurrency_slot_timeouts_present" in codes

    asyncio.run(scenario())
