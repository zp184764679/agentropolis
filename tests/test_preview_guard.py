"""Regression tests for preview-route control-plane guardrails."""

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
    get_preview_guard_state,
    make_agent_preview_write_guard,
    require_agent_preview_write,
    reset_preview_guard_state,
)
from agentropolis.config import settings
from agentropolis.database import get_session
from agentropolis.main import app
from agentropolis.models import Base


def _admin_headers(token: str = "root-token") -> dict[str, str]:
    return {"X-Control-Plane-Token": token}


@asynccontextmanager
async def _preview_client(*, agent_id: int | None = None):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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
        await engine.dispose()


def test_preview_guard_rate_limits_agent_mutations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PREVIEW_AGENT_MUTATIONS_PER_WINDOW", 1)
    monkeypatch.setattr(settings, "PREVIEW_MUTATION_WINDOW_SECONDS", 60)
    reset_preview_guard_state()

    async def scenario() -> None:
        actor = SimpleNamespace(id=42)

        await require_agent_preview_write(actor)

        with pytest.raises(HTTPException) as excinfo:
            await require_agent_preview_write(actor)

        assert excinfo.value.status_code == 429
        assert excinfo.value.detail == "Preview mutation rate limit exceeded."

    try:
        asyncio.run(scenario())
    finally:
        reset_preview_guard_state()


def test_preview_guard_enforces_family_specific_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PREVIEW_TRANSPORT_MUTATIONS_PER_WINDOW", 1)
    monkeypatch.setattr(settings, "PREVIEW_MUTATION_WINDOW_SECONDS", 60)
    reset_preview_guard_state()

    async def scenario() -> None:
        actor = SimpleNamespace(id=99)
        transport_guard = make_agent_preview_write_guard("transport")

        await transport_guard(actor)

        with pytest.raises(HTTPException) as excinfo:
            await transport_guard(actor)

        assert excinfo.value.status_code == 429
        assert excinfo.value.detail == "Preview transport mutation rate limit exceeded."

    try:
        asyncio.run(scenario())
    finally:
        reset_preview_guard_state()


def test_preview_surface_kill_switch_blocks_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PREVIEW_SURFACE_ENABLED", False)
    reset_preview_guard_state()

    async def scenario() -> None:
        async with _preview_client() as client:
            response = await client.get("/api/world/map")

        assert response.status_code == 503
        assert response.json()["detail"] == "Preview surface is disabled by runtime policy."

    asyncio.run(scenario())


def test_control_plane_admin_endpoint_requires_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONTROL_PLANE_ADMIN_TOKEN", "root-token")
    reset_preview_guard_state()

    async def scenario() -> None:
        async with _preview_client() as client:
            response = await client.get("/meta/control-plane")

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid control-plane admin token."

    asyncio.run(scenario())


def test_control_plane_admin_endpoint_updates_runtime_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONTROL_PLANE_ADMIN_TOKEN", "root-token")
    reset_preview_guard_state()

    async def scenario() -> None:
        async with _preview_client(agent_id=7) as client:
            before = await client.get("/meta/control-plane", headers=_admin_headers())
            assert before.status_code == 200
            assert before.json()["degraded_mode"] is False

            updated = await client.put(
                "/meta/control-plane",
                headers=_admin_headers(),
                json={"degraded_mode": True, "writes_enabled": True},
            )
            assert updated.status_code == 200
            assert updated.json()["degraded_mode"] is True
            world_guard = make_agent_preview_write_guard("world")
            agent_guard = make_agent_preview_write_guard(
                "agent_self",
                allow_in_degraded_mode=True,
            )
            actor = SimpleNamespace(id=7)

            with pytest.raises(HTTPException) as excinfo:
                await world_guard(actor)

            assert excinfo.value.status_code == 503
            assert excinfo.value.detail == "Preview world mutations are disabled in degraded mode."

            await agent_guard(actor)
            assert get_preview_guard_state()["degraded_mode"] is True

    try:
        asyncio.run(scenario())
    finally:
        reset_preview_guard_state()


def test_control_plane_admin_reset_clears_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONTROL_PLANE_ADMIN_TOKEN", "root-token")
    monkeypatch.setattr(settings, "PREVIEW_SURFACE_ENABLED", True)
    reset_preview_guard_state()

    async def scenario() -> None:
        async with _preview_client() as client:
            updated = await client.put(
                "/meta/control-plane",
                headers=_admin_headers(),
                json={"surface_enabled": False},
            )
            assert updated.status_code == 200
            assert updated.json()["surface_enabled"] is False

            reset_response = await client.post(
                "/meta/control-plane/reset-rate-limits",
                headers=_admin_headers(),
            )
            assert reset_response.status_code == 200

            current = await client.get("/meta/control-plane", headers=_admin_headers())
            assert current.status_code == 200
            assert current.json()["surface_enabled"] is True

    asyncio.run(scenario())


def test_control_plane_agent_policy_blocks_unauthorized_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONTROL_PLANE_ADMIN_TOKEN", "root-token")
    reset_preview_guard_state()

    async def scenario() -> None:
        async with _preview_client(agent_id=7) as client:
            policy = await client.put(
                "/meta/control-plane/agents/7/policy",
                headers=_admin_headers(),
                json={"allowed_families": ["agent_self"]},
            )
            assert policy.status_code == 200

            response = await client.post(
                "/api/world/travel",
                json={"to_region_id": 2},
            )

        assert response.status_code == 403
        assert response.json()["detail"] == (
            "Preview world access is not allowed for agent 7."
        )

    asyncio.run(scenario())


def test_control_plane_agent_policy_blocks_authenticated_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONTROL_PLANE_ADMIN_TOKEN", "root-token")
    reset_preview_guard_state()

    async def scenario() -> None:
        async with _preview_client(agent_id=7) as client:
            policy = await client.put(
                "/meta/control-plane/agents/7/policy",
                headers=_admin_headers(),
                json={"allowed_families": ["agent_self"]},
            )
            assert policy.status_code == 200

            response = await client.get("/api/agent/decisions")

        assert response.status_code == 403
        assert response.json()["detail"] == (
            "Preview strategy access is not allowed for agent 7."
        )

    asyncio.run(scenario())


def test_public_preview_reads_remain_surface_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONTROL_PLANE_ADMIN_TOKEN", "root-token")
    reset_preview_guard_state()

    async def scenario() -> None:
        async with _preview_client(agent_id=7) as client:
            policy = await client.put(
                "/meta/control-plane/agents/7/policy",
                headers=_admin_headers(),
                json={"allowed_families": ["agent_self"]},
            )
            assert policy.status_code == 200

            response = await client.get("/api/world/map")

        assert response.status_code == 200
        assert response.json() == {"regions": []}

    asyncio.run(scenario())


def test_control_plane_agent_policy_consumes_family_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONTROL_PLANE_ADMIN_TOKEN", "root-token")
    reset_preview_guard_state()

    async def scenario() -> None:
        async with _preview_client(agent_id=7) as client:
            policy = await client.put(
                "/meta/control-plane/agents/7/policy",
                headers=_admin_headers(),
                json={"family_budgets": {"transport": 1}},
            )
            assert policy.status_code == 200
            assert policy.json()["family_budgets"]["transport"] == 1

            transport_guard = make_agent_preview_write_guard("transport")
            actor = SimpleNamespace(id=7)

            await transport_guard(actor)

            with pytest.raises(HTTPException) as excinfo:
                await transport_guard(actor)

            assert excinfo.value.status_code == 403
            assert excinfo.value.detail == "Preview transport budget exhausted for agent 7."

    try:
        asyncio.run(scenario())
    finally:
        reset_preview_guard_state()


def test_control_plane_audit_log_records_admin_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CONTROL_PLANE_ADMIN_TOKEN", "root-token")
    reset_preview_guard_state()

    async def scenario() -> None:
        async with _preview_client() as client:
            updated = await client.put(
                "/meta/control-plane",
                headers=_admin_headers(),
                json={"degraded_mode": True},
            )
            assert updated.status_code == 200

            policy = await client.put(
                "/meta/control-plane/agents/9/policy",
                headers=_admin_headers(),
                json={"allowed_families": ["strategy"], "family_budgets": {"strategy": 2}},
            )
            assert policy.status_code == 200

            audit = await client.get(
                "/meta/control-plane/audit",
                headers=_admin_headers(),
                params={"limit": 5},
            )
            assert audit.status_code == 200

            entries = audit.json()["entries"]
            actions = {entry["action"] for entry in entries}

            assert "update_preview_runtime_policy" in actions
            assert "upsert_agent_preview_policy" in actions
            assert all(entry["actor"].startswith("control-plane-admin:") for entry in entries)

    asyncio.run(scenario())


def test_preview_write_gate_blocks_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PREVIEW_WRITES_ENABLED", False)
    reset_preview_guard_state()

    async def scenario() -> None:
        async with _preview_client() as client:
            response = await client.post(
                "/api/agent/register",
                json={"name": "Blocked Agent"},
            )

        assert response.status_code == 503
        assert response.json()["detail"] == "Preview write operations are disabled by runtime policy."

    asyncio.run(scenario())


def test_warfare_toggle_blocks_preview_mutations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "WARFARE_MUTATIONS_ENABLED", False)
    reset_preview_guard_state()

    async def scenario() -> None:
        async with _preview_client(agent_id=7) as client:
            response = await client.post(
                "/api/warfare/contracts",
                json={
                    "mission_type": "raid_transport",
                    "target_region_id": 1,
                    "reward_per_agent": 100,
                    "max_agents": 1,
                },
            )

        assert response.status_code == 503
        assert response.json()["detail"] == (
            "Warfare preview mutations are disabled by runtime policy."
        )

    asyncio.run(scenario())
