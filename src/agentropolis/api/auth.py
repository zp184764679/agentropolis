"""Agent-first API-key authentication dependencies for FastAPI."""

import hashlib
from typing import Any

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.control_contract import AUTH_ERROR_CODES
from agentropolis.database import get_session
from agentropolis.models import Company
from agentropolis.services.company_svc import get_active_company_model

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_api_key(api_key: str) -> str:
    """Hash an API key with SHA-256 for storage."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def _require_api_key(api_key: str | None) -> str:
    """Validate presence of the API key and return its hash."""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
            headers={"X-Agentropolis-Error-Code": "auth_api_key_missing"},
        )
    return hash_api_key(api_key)


async def get_current_agent(
    api_key: str | None = Security(api_key_header),
    request: Request = None,
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Migration-safe Agent auth entrypoint.

    This function exists so target-agent route modules can import a stable symbol
    during the migration from company-auth to agent-auth. In the current scaffold
    runtime it may intentionally return 501 when the Agent auth surface is not yet
    fully wired into models, schema, and database state.
    """
    agent = await resolve_agent_from_api_key(session, api_key)
    if request is not None:
        request.state.authenticated_actor_kind = "agent"
        request.state.authenticated_actor_key = f"agent:{agent.id}"
    return agent


async def resolve_agent_from_api_key(
    session: AsyncSession,
    api_key: str | None,
) -> Any:
    """Resolve an API key to an active agent without FastAPI dependency wiring."""
    key_hash = _require_api_key(api_key)

    try:
        from agentropolis.models.agent import Agent  # type: ignore
    except Exception as exc:  # pragma: no cover - defensive migration guard
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=AUTH_ERROR_CODES["auth_agent_model_unavailable"],
            headers={"X-Agentropolis-Error-Code": "auth_agent_model_unavailable"},
        ) from exc

    try:
        result = await session.execute(
            select(Agent).where(Agent.api_key_hash == key_hash, Agent.is_active.is_(True))
        )
    except Exception as exc:  # pragma: no cover - defensive migration guard
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=AUTH_ERROR_CODES["auth_agent_model_unavailable"],
            headers={"X-Agentropolis-Error-Code": "auth_agent_model_unavailable"},
        ) from exc

    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key for agent auth",
            headers={"X-Agentropolis-Error-Code": "auth_agent_api_key_invalid"},
        )
    return agent


async def resolve_active_company_for_agent(
    session: AsyncSession,
    agent_id: int,
) -> Company:
    """Resolve the active company owned by an authenticated agent."""
    company = await get_active_company_model(session, agent_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent does not have an active company",
            headers={"X-Agentropolis-Error-Code": "agent_company_not_found"},
        )
    return company


async def get_current_agent_company(
    agent: Any = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
) -> Company:
    """Resolve the active company for the authenticated agent."""
    return await resolve_active_company_for_agent(session, agent.id)


async def get_optional_current_agent_company(
    api_key: str | None = Security(api_key_header),
    request: Request = None,
    session: AsyncSession = Depends(get_session),
) -> Company | None:
    """Resolve the active company for an authenticated agent when present."""
    if not api_key:
        return None

    agent = await get_current_agent(api_key=api_key, request=request, session=session)
    return await resolve_active_company_for_agent(session, agent.id)
