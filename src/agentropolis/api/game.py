"""Game status and leaderboard REST API endpoints.

Dependencies: services/leaderboard.py, services/game_engine.py
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_company
from agentropolis.api.schemas import GameStatus, LeaderboardResponse
from agentropolis.database import get_session
from agentropolis.models import Company

router = APIRouter(prefix="/game", tags=["game"])


@router.get("/status", response_model=GameStatus)
async def get_game_status(session: AsyncSession = Depends(get_session)):
    """Get current game state (tick, timing, player count)."""
    raise NotImplementedError("Issue #12: Implement game API endpoints")


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    metric: str = "net_worth",
    company: Company | None = Depends(get_current_company),
    session: AsyncSession = Depends(get_session),
):
    """Get the leaderboard ranked by a metric."""
    raise NotImplementedError("Issue #12: Implement game API endpoints")
