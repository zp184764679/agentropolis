"""Game status and leaderboard REST API endpoints.

Dependencies: services/leaderboard.py, services/game_engine.py
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_optional_current_company
from agentropolis.api.preview_guard import ERROR_CODE_HEADER
from agentropolis.api.schemas import (
    GameStatus,
    HousekeepingHistoryResponse,
    HousekeepingStatusResponse,
    LeaderboardResponse,
)
from agentropolis.database import get_session
from agentropolis.models import Company, GameState, HousekeepingLog
from agentropolis.services.game_engine import (
    get_housekeeping_history as get_housekeeping_history_svc,
    get_housekeeping_status as get_housekeeping_status_svc,
)
from agentropolis.services import leaderboard as leaderboard_svc

router = APIRouter(prefix="/game", tags=["game"])


@router.get("/status", response_model=GameStatus)
async def get_game_status(session: AsyncSession = Depends(get_session)):
    """Get current game state (tick, timing, player count)."""
    state = await session.get(GameState, 1)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Game state has not been seeded yet.",
            headers={ERROR_CODE_HEADER: "game_state_unavailable"},
        )

    total_companies = int(
        (await session.execute(select(func.count(Company.id)))).scalar_one() or 0
    )
    active_companies = int(
        (
            await session.execute(select(func.count(Company.id)).where(Company.is_active.is_(True)))
        ).scalar_one()
        or 0
    )

    next_tick_in_seconds = None
    if state.is_running and state.last_tick_at is not None:
        last_tick_at = state.last_tick_at
        if last_tick_at.tzinfo is None:
            last_tick_at = last_tick_at.replace(tzinfo=UTC)
        elapsed = (datetime.now(UTC) - last_tick_at).total_seconds()
        next_tick_in_seconds = max(float(state.tick_interval_seconds) - elapsed, 0.0)

    return {
        "current_tick": state.current_tick,
        "tick_interval_seconds": state.tick_interval_seconds,
        "is_running": state.is_running,
        "next_tick_in_seconds": next_tick_in_seconds,
        "total_companies": total_companies,
        "active_companies": active_companies,
    }


@router.get("/housekeeping/status", response_model=HousekeepingStatusResponse)
async def get_housekeeping_status(session: AsyncSession = Depends(get_session)):
    """Return the latest housekeeping summary with GameState fallback."""
    return await get_housekeeping_status_svc(session)


@router.get("/housekeeping/history", response_model=HousekeepingHistoryResponse)
async def get_housekeeping_history(
    limit: int = Query(default=10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Return recent persisted housekeeping logs."""
    entries = await get_housekeeping_history_svc(session, limit=limit)
    total = int(
        (await session.execute(select(func.count(HousekeepingLog.id)))).scalar_one() or 0
    )
    return {
        "entries": entries,
        "total": total,
    }


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    metric: str = "net_worth",
    company: Company | None = Depends(get_optional_current_company),
    session: AsyncSession = Depends(get_session),
):
    """Get the leaderboard ranked by a metric."""
    try:
        ranked = await leaderboard_svc.get_leaderboard(session, metric=metric, limit=None)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
            headers={ERROR_CODE_HEADER: "leaderboard_metric_invalid"},
        ) from None

    entries = [
        {
            "rank": row["rank"],
            "company_name": row["company_name"],
            "net_worth": row["net_worth"],
            "balance": row["balance"],
            "worker_count": row["worker_count"],
            "building_count": row["building_count"],
        }
        for row in ranked[:20]
    ]
    your_rank = None
    if company is not None:
        your_rank = next(
            (row["rank"] for row in ranked if row["company_id"] == company.id),
            None,
        )

    return {
        "metric": metric.lower(),
        "entries": entries,
        "your_rank": your_rank,
    }
