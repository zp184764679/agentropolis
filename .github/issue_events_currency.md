## Overview

Implement World Events service + Currency service — dynamic world events and inflation monitoring.

World events modify region properties temporarily. Currency service tracks money supply and inflation.

## Files

- **Create**: `src/agentropolis/services/event_svc.py`
- **Create**: `src/agentropolis/services/currency_svc.py`
- **DO NOT TOUCH**: Model files, other services

## event_svc.py

```python
async def create_event(
    session: AsyncSession, event_type: str, region_id: int,
    effects: dict, duration_hours: int, description: str = "",
    now: datetime | None = None,
) -> dict:
    """Create a world event.
    Effects dict examples:
    - {"resource_multiplier": {"H2O": 0.5}} — drought halves water output
    - {"resource_multiplier": {"ORE": 2.0}} — vein discovery doubles ore
    - {"danger_modifier": 3} — bandit raid increases danger
    - {"tax_modifier": -0.03} — market fair reduces tax 3%
    Returns: {"event_id", "event_type", "region_id", "starts_at", "ends_at"}"""

async def get_active_events(
    session: AsyncSession, region_id: int | None = None, now: datetime | None = None,
) -> list[dict]:
    """Get active events, optionally for a specific region."""

async def apply_event_effects(
    session: AsyncSession, region_id: int, base_value: float, resource_ticker: str | None = None,
    effect_key: str = "resource_multiplier", now: datetime | None = None,
) -> float:
    """Apply active event effects to a base value.
    Stacks multiplicatively. Returns modified value."""

async def expire_events(session: AsyncSession, now: datetime | None = None) -> int:
    """Deactivate expired events. Called by housekeeping. Returns count."""

async def generate_random_event(
    session: AsyncSession, now: datetime | None = None,
) -> dict | None:
    """Randomly generate a world event. 10% chance per housekeeping sweep per region.
    Event types: drought, vein_discovery, bandit_raid, market_fair, plague, harvest_festival
    Returns event dict or None if no event generated."""
```

### Event Types
```python
EVENT_TEMPLATES = {
    "drought": {"effects": {"resource_multiplier": {"H2O": 0.5, "CRP": 0.7}}, "duration_hours": 4},
    "vein_discovery": {"effects": {"resource_multiplier": {"ORE": 2.0}}, "duration_hours": 2},
    "bandit_raid": {"effects": {"danger_modifier": 5}, "duration_hours": 1},
    "market_fair": {"effects": {"tax_modifier": -0.03}, "duration_hours": 3},
    "plague": {"effects": {"satisfaction_modifier": -20}, "duration_hours": 6},
    "harvest_festival": {"effects": {"resource_multiplier": {"CRP": 1.5, "RAT": 1.3}}, "duration_hours": 4},
}
```

## currency_svc.py

```python
async def get_money_supply(session: AsyncSession) -> dict:
    """Calculate total money supply.
    M1 = sum(all agent personal_balance) + sum(all company balance)
    M2 = M1 + sum(all guild treasury) + sum(all region treasury)
    Returns: {"m1": int, "m2": int, "agent_total": int, "company_total": int,
              "guild_total": int, "region_total": int}"""

async def get_inflation_index(session: AsyncSession) -> dict:
    """Calculate inflation index based on price changes.
    Compare current average prices vs base_price for all resources.
    index = avg(current_price / base_price) across all resources
    Returns: {"inflation_index": float, "per_resource": {ticker: ratio}}"""

async def update_game_state_economics(session: AsyncSession) -> dict:
    """Update GameState with current economic data. Called by housekeeping.
    Updates: total_currency_supply, inflation_index
    Returns: {"total_currency_supply", "inflation_index"}"""

async def format_copper(amount: int) -> dict:
    """Convert copper to display format.
    Returns: {"gold": amount // 10000, "silver": (amount % 10000) // 100,
              "copper": amount % 100, "display": "1g 23s 45c"}"""
```

## Acceptance Criteria

- [ ] Event CRUD with duration
- [ ] 6 event templates
- [ ] Random event generation
- [ ] Event effect application (multiplicative stacking)
- [ ] Event expiration
- [ ] Money supply calculation (M1, M2)
- [ ] Inflation index tracking
- [ ] GameState economics update
- [ ] Copper display formatting

## Dependencies

- **Depends on**: #16 (Foundation)
- **Blocks**: game_engine event step
