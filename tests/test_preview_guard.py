"""Regression tests for DB-backed preview control-plane guardrails."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentropolis.api.auth import get_current_agent
from agentropolis.api.preview_guard import (
    ERROR_CODE_HEADER,
    get_preview_guard_state,
    make_agent_preview_write_guard,
    reset_preview_guard_state,
    upsert_agent_preview_policy,
)
from agentropolis.config import settings
from agentropolis.database import get_session
from agentropolis.main import app
from agentropolis.middleware import REQUEST_ID_HEADER
from agentropolis.models import Base
from agentropolis.services.agent_svc import register_agent
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world


def _admin_headers(token: str = "root-token") -> dict[str, str]:
    return {"X-Control-Plane-Token": token}


def _assert_error_contract(
    response,
    *,
    status_code: int,
    error_code: str,
    detail: str,
) -> None:
    body = response.json()
    assert response.status_code == status_code
    assert body["detail"] == detail
    assert body["error_code"] == error_code
    assert response.headers[ERROR_CODE_HEADER] == error_code
    assert response.headers[REQUEST_ID_HEADER]
    assert body["request_id"] == response.headers[REQUEST_ID_HEADER]


async def _create_seeded_engine(*, agent_names: list[str] | None = None):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    agent_ids: list[int] = []
    async with session_factory() as session:
        await seed_game_data(session)
        await seed_world(session)
        for name in agent_names or []:
            created = await register_agent(session, name, None)
            agent_ids.append(created["agent_id"])
        await session.commit()

    return engine, session_factory, agent_ids


@asynccontextmanager
async def _preview_client(session_factory, *, agent_id: int | None = None):
    async def override_get_session():
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = override_get_session
    if agent_id is not None:
        async def override_current_agent():
            return SimpleNamespace(id=agent_id)

        app.dependency_overrides[get_current_agent] = override_current_agent

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        reset_preview_guard_state()


def test_preview_surface_kill_switch_blocks_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONTROL_PLANE_ADMIN_TOKEN", "root-token")

    async def scenario() -> None:
        engine, session_factory, _ = await _create_seeded_engine()
        try:
            async with _preview_client(session_factory) as client:
                update_response = await client.put(
                    "/meta/control-plane",
                    headers=_admin_headers(),
                    json={"surface_enabled": False},
                )
                assert update_response.status_code == 200

                response = await client.get("/api/world/map")

            _assert_error_contract(
                response,
                status_code=503,
                error_code="preview_surface_disabled",
                detail="Preview surface is disabled by runtime policy.",
            )
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_control_plane_admin_endpoint_requires_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONTROL_PLANE_ADMIN_TOKEN", "root-token")

    async def scenario() -> None:
        engine, session_factory, _ = await _create_seeded_engine()
        try:
            async with _preview_client(session_factory) as client:
                response = await client.get("/meta/control-plane")

            _assert_error_contract(
                response,
                status_code=401,
                error_code="control_plane_admin_invalid",
                detail="Invalid control-plane admin token.",
            )
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_control_plane_policy_persists_across_client_restarts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONTROL_PLANE_ADMIN_TOKEN", "root-token")

    async def scenario() -> None:
        engine, session_factory, agent_ids = await _create_seeded_engine(agent_names=["Policy Agent"])
        agent_id = agent_ids[0]
        try:
            async with _preview_client(session_factory, agent_id=agent_id) as client:
                response = await client.put(
                    f"/meta/control-plane/agents/{agent_id}/policy",
                    headers=_admin_headers(),
                    json={"allowed_families": ["agent_self"]},
                )
                assert response.status_code == 200

            async with _preview_client(session_factory, agent_id=agent_id) as client:
                snapshot = await client.get("/meta/control-plane", headers=_admin_headers())
                blocked = await client.get("/api/agent/decisions")

            assert snapshot.status_code == 200
            assert snapshot.json()["persistent_policy_store"] == "database"
            assert snapshot.json()["agent_policies"][0]["agent_id"] == agent_id
            assert blocked.status_code == 403
            assert blocked.json()["error_code"] == "preview_strategy_access_denied"
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_control_plane_budget_consumption_and_refill_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONTROL_PLANE_ADMIN_TOKEN", "root-token")

    async def scenario() -> None:
        engine, session_factory, agent_ids = await _create_seeded_engine(agent_names=["Budget Agent"])
        agent_id = agent_ids[0]
        try:
            async with session_factory() as session:
                await upsert_agent_preview_policy(
                    session,
                    agent_id,
                    family_budgets={"transport": 1},
                )
                await session.commit()

            transport_guard = make_agent_preview_write_guard("transport")
            actor = SimpleNamespace(id=agent_id)

            async with session_factory() as session:
                await transport_guard(actor, session)
                await session.commit()

            async with session_factory() as session:
                with pytest.raises(HTTPException) as excinfo:
                    await transport_guard(actor, session)
                assert excinfo.value.status_code == 403
                assert excinfo.value.detail == (
                    f"Preview transport budget exhausted for agent {agent_id}."
                )

            async with _preview_client(session_factory, agent_id=agent_id) as client:
                refill = await client.post(
                    f"/meta/control-plane/agents/{agent_id}/refill-budget",
                    headers=_admin_headers(),
                    json={
                        "increments": {"transport": 2},
                        "reason_code": "quota_refill",
                        "note": "top up transport",
                    },
                )
                assert refill.status_code == 200

            async with session_factory() as session:
                state = await get_preview_guard_state(session)
                assert state["agent_policy_count"] == 1
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_reset_rate_limits_preserves_durable_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONTROL_PLANE_ADMIN_TOKEN", "root-token")

    async def scenario() -> None:
        engine, session_factory, agent_ids = await _create_seeded_engine(agent_names=["Reset Agent"])
        agent_id = agent_ids[0]
        try:
            async with _preview_client(session_factory, agent_id=agent_id) as client:
                policy = await client.put(
                    f"/meta/control-plane/agents/{agent_id}/policy",
                    headers=_admin_headers(),
                    json={"allowed_families": ["agent_self"], "family_budgets": {"agent_self": 2}},
                )
                assert policy.status_code == 200

                update = await client.put(
                    "/meta/control-plane",
                    headers=_admin_headers(),
                    json={"degraded_mode": True},
                )
                assert update.status_code == 200

                reset_response = await client.post(
                    "/meta/control-plane/reset-rate-limits",
                    headers=_admin_headers(),
                    json={"reason_code": "cleanup", "note": "clear buckets only"},
                )
                assert reset_response.status_code == 200

                snapshot = await client.get("/meta/control-plane", headers=_admin_headers())

            assert snapshot.status_code == 200
            assert snapshot.json()["degraded_mode"] is True
            assert snapshot.json()["agent_policy_count"] == 1
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_control_plane_audit_filtering_by_request_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONTROL_PLANE_ADMIN_TOKEN", "root-token")

    async def scenario() -> None:
        engine, session_factory, agent_ids = await _create_seeded_engine(agent_names=["Audit Agent"])
        agent_id = agent_ids[0]
        try:
            async with _preview_client(session_factory, agent_id=agent_id) as client:
                first = await client.put(
                    f"/meta/control-plane/agents/{agent_id}/policy",
                    headers={**_admin_headers(), REQUEST_ID_HEADER: "req-audit-first"},
                    json={"allowed_families": ["strategy"]},
                )
                assert first.status_code == 200

                second = await client.post(
                    f"/meta/control-plane/agents/{agent_id}/refill-budget",
                    headers={**_admin_headers(), REQUEST_ID_HEADER: "req-audit-second"},
                    json={
                        "increments": {"strategy": 2},
                        "reason_code": "quota_refill",
                        "note": "top up strategy budget",
                    },
                )
                assert second.status_code == 200

                audit = await client.get(
                    "/meta/control-plane/audit",
                    headers=_admin_headers(),
                    params={"request_id": "req-audit-second"},
                )

            assert audit.status_code == 200
            entries = audit.json()["entries"]
            assert len(entries) == 1
            assert entries[0]["request_id"] == "req-audit-second"
            assert entries[0]["action"] == "refill_agent_preview_budget"
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_request_validation_errors_expose_stable_error_contract() -> None:
    async def scenario() -> None:
        engine, session_factory, _ = await _create_seeded_engine()
        try:
            async with _preview_client(session_factory) as client:
                response = await client.post("/api/agent/register", json={})

            assert response.status_code == 422
            assert response.json()["error_code"] == "request_validation_failed"
            assert response.headers[ERROR_CODE_HEADER] == "request_validation_failed"
            assert response.headers[REQUEST_ID_HEADER]
            assert response.json()["request_id"] == response.headers[REQUEST_ID_HEADER]
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_runtime_metadata_reports_db_backed_control_plane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONTROL_PLANE_ADMIN_TOKEN", "root-token")

    async def scenario() -> None:
        engine, session_factory, _ = await _create_seeded_engine()
        try:
            async with _preview_client(session_factory) as client:
                response = await client.get("/meta/runtime")

            assert response.status_code == 200
            body = response.json()
            assert body["control_plane_surface"]["scope"] == "db_persisted_preview_policy"
            assert body["control_plane_surface"]["persistent"] is True
            assert body["preview_guard"]["persistent_policy_store"] == "database"
        finally:
            await engine.dispose()

    asyncio.run(scenario())
