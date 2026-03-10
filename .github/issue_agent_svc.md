## Overview

Implement Agent service + Agent vitals — registration, status, survival actions (eat/drink/rest), death/respawn.

Agent is the player entity. Has personal vitals that decay over time (lazy settlement, same pattern as NPC consumption). Agent can eat, drink, rest to restore vitals.

## Files

- **Create**: `src/agentropolis/services/agent_svc.py`
- **Create**: `src/agentropolis/services/agent_vitals.py`
- **DO NOT TOUCH**: Model files, other services

## agent_svc.py — Agent Management

```python
async def register_agent(session: AsyncSession, name: str) -> dict:
    """Register a new Agent.
    1. Generate API key (secrets.token_hex(32))
    2. Hash with SHA-256, store hash
    3. Assign to a random CORE region as home + current
    4. Set initial vitals: health=100, hunger=100, thirst=100, energy=100
    5. Set personal_balance = AGENT_INITIAL_BALANCE (config)
    6. Set last_vitals_at = now

    Returns: {"agent_id", "name", "api_key" (plaintext, only returned once),
              "home_region_id", "balance"}
    Raises: ValueError if name taken"""

async def get_agent_status(
    session: AsyncSession, agent_id: int, now: datetime | None = None,
) -> dict:
    """Settle vitals first, then return full status.
    Returns: {"agent_id", "name", "health", "hunger", "thirst", "energy",
              "happiness", "reputation", "current_region_id", "region_name",
              "personal_balance", "career_path", "is_alive", "skills": [...],
              "companies": [...], "is_traveling": bool}"""

async def eat(
    session: AsyncSession, agent_id: int, resource_id: int, quantity: int,
    now: datetime | None = None,
) -> dict:
    """Consume food from personal inventory to restore hunger.
    resource must be category=CONSUMABLE (RAT or similar).
    hunger_restored = quantity * 10 (capped at 100).
    Returns: {"hunger", "consumed": int}
    Raises: ValueError if insufficient inventory or wrong resource type"""

async def drink(
    session: AsyncSession, agent_id: int, resource_id: int, quantity: int,
    now: datetime | None = None,
) -> dict:
    """Consume water from personal inventory to restore thirst.
    thirst_restored = quantity * 12 (capped at 100).
    Returns: {"thirst", "consumed": int}"""

async def rest(
    session: AsyncSession, agent_id: int, duration_seconds: int,
    now: datetime | None = None,
) -> dict:
    """Rest to restore energy. Agent must not be traveling.
    energy_restored = duration_seconds * (100.0 / 3600) (1 hour for full restore).
    Also recovers health slightly: +1 per 60s if hunger > 50 and thirst > 50.
    Returns: {"energy", "health", "rested_seconds": int}"""

async def respawn(session: AsyncSession, agent_id: int) -> dict:
    """Respawn dead agent at home region.
    Restore health=50, hunger=50, thirst=50, energy=50.
    Penalty: lose AGENT_RESPAWN_PENALTY fraction of personal_balance.
    Returns: {"agent_id", "region_id", "health", "balance"}"""
```

## agent_vitals.py — Lazy Vitals Settlement

```python
async def settle_agent_vitals(
    session: AsyncSession, agent_id: int, now: datetime | None = None,
) -> dict:
    """Settle Agent vitals based on elapsed time.
    1. Load Agent (FOR UPDATE)
    2. If not is_alive or last_vitals_at is None, skip
    3. elapsed = now - last_vitals_at
    4. Decay:
       hunger -= HUNGER_DECAY_PER_SECOND * elapsed (floor 0)
       thirst -= THIRST_DECAY_PER_SECOND * elapsed (floor 0)
       energy -= ENERGY_DECAY_PER_SECOND * elapsed (floor 0)
    5. Health damage:
       if hunger == 0: health -= HEALTH_DAMAGE_HUNGER * elapsed
       if thirst == 0: health -= HEALTH_DAMAGE_THIRST * elapsed
       health = max(0, health)
    6. If health == 0: is_alive = False (death!)
    7. Update last_vitals_at = now
    Returns: {"hunger", "thirst", "energy", "health", "is_alive", "elapsed_seconds"}"""

async def settle_all_agent_vitals(
    session: AsyncSession, now: datetime | None = None,
) -> dict:
    """Settle vitals for all active, alive agents. Used by housekeeping.
    Returns: {"agents_processed", "deaths": int}"""
```

## Implementation Rules

1. `settle_agent_vitals` uses FOR UPDATE on Agent row
2. Vitals are float 0-100 (not integer — smooth decay)
3. `eat`/`drink` settle vitals first, then apply restoration
4. `eat`/`drink` consume from Agent's personal inventory (agent_id, not company_id)
5. `rest` requires agent NOT be traveling (check TravelQueue)
6. Death: set `is_alive = False`, agent can only call `respawn`
7. Respawn: teleport to home_region, restore partial vitals, apply balance penalty
8. `get_agent_status` also checks TravelQueue for is_traveling

## Acceptance Criteria

- [ ] Agent registration with API key generation
- [ ] Lazy vitals settlement (same pattern as consumption)
- [ ] eat/drink/rest mechanics
- [ ] Death at health=0
- [ ] Respawn with penalty
- [ ] FOR UPDATE locking
- [ ] `now` parameter for testability
- [ ] settle_all for housekeeping

## Dependencies

- **Depends on**: #16 (Foundation), #17 (inventory_svc for personal inventory)
- **Blocks**: API routes, game_engine vitals step
