## Overview

Update Game API endpoints + add Leaderboard endpoints.

## Files

- **Modify**: `src/agentropolis/api/game.py`
- **DO NOT TOUCH**: Other API files, services, models

## api/game.py Changes

```python
router = APIRouter(prefix="/game", tags=["game"])

GET  /api/game/status            → GameStatus
    No auth.
    Returns: is_running, started_at, uptime, total_agents, active_agents,
             total_companies, total_regions, current_season, inflation_index

GET  /api/game/leaderboard       → LeaderboardResponse
    Query: metric=net_worth, region_id=None, limit=20
    Optional auth (for your_rank).
    Calls: leaderboard.get_leaderboard()

GET  /api/game/resources         → list[ResourceInfo]
    No auth. List all resources with base prices and properties.

GET  /api/game/economics         → EconomicsResponse
    No auth.
    Returns: money_supply (M1, M2), inflation_index, per_resource price ratios

GET  /api/game/events            → list[WorldEventInfo]
    Query: region_id=None, active_only=True
    No auth. Calls: event_svc.get_active_events()
```

## New Schemas

```python
class GameStatus(BaseModel):
    is_running: bool
    started_at: str | None
    uptime_seconds: float | None
    total_agents: int
    active_agents: int
    total_companies: int
    active_companies: int
    total_regions: int
    current_season: str
    inflation_index: float

class EconomicsResponse(BaseModel):
    m1: int  # copper
    m2: int
    inflation_index: float
    per_resource: dict[str, float]  # {ticker: price_ratio}

class LeaderboardResponse(BaseModel):
    metric: str
    entries: list[LeaderboardEntry]
    your_rank: int | None = None
```

## Acceptance Criteria

- [ ] Game status includes new fields
- [ ] Leaderboard with optional region filter
- [ ] Resources endpoint with evolution fields
- [ ] Economics summary
- [ ] Events listing

## Dependencies

- **Depends on**: #16 (Foundation), #22 (leaderboard), #28 (events_currency)
- **Blocks**: None
