"""Shared FastAPI dependencies.

Note: this module currently re-exports the legacy company-auth dependency.
As the control-plane model stabilizes, dependency exports should converge on the
Agent-based auth/authz surface defined in `PLAN.md`.
"""

from agentropolis.api.auth import get_current_agent, get_current_company
from agentropolis.control_contract import (
    AUTHORIZATION_ACTOR_KINDS,
    build_authorization_scope_catalog,
    build_control_contract_catalog,
)
from agentropolis.database import get_session

__all__ = [
    "get_session",
    "get_current_company",
    "get_current_agent",
    "build_authorization_scope_catalog",
    "build_control_contract_catalog",
    "AUTHORIZATION_ACTOR_KINDS",
]
