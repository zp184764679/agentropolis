"""Shared FastAPI dependencies."""

from agentropolis.api.auth import get_current_company
from agentropolis.database import get_session

__all__ = ["get_session", "get_current_company"]
