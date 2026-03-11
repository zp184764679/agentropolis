"""Shared FastAPI dependencies for the agent-auth runtime surface."""

from agentropolis.api.auth import get_current_agent, get_current_agent_company
from agentropolis.control_contract import (
    AUTHORIZATION_ACTOR_KINDS,
    build_authorization_scope_catalog,
    build_control_contract_catalog,
)
from agentropolis.database import get_session

__all__ = [
    "get_session",
    "get_current_agent",
    "get_current_agent_company",
    "build_authorization_scope_catalog",
    "build_control_contract_catalog",
    "AUTHORIZATION_ACTOR_KINDS",
]
