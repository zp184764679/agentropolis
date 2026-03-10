## Overview

Implement Guild service + Diplomacy service — guild management, agent relationships, treaties.

Guilds are player organizations with treasury, ranks, and maintenance costs. Diplomacy manages inter-agent and inter-guild relations and treaties.

## Files

- **Create**: `src/agentropolis/services/guild_svc.py`
- **Create**: `src/agentropolis/services/diplomacy_svc.py`
- **DO NOT TOUCH**: Model files, other services

## guild_svc.py

```python
async def create_guild(
    session: AsyncSession, agent_id: int, name: str, region_id: int,
) -> dict:
    """Create a guild. Agent becomes Leader.
    Initial treasury = 0. Level = 1. Maintenance = 100 gold + members^1.8 * 10 copper/day.
    Returns: {"guild_id", "name", "level", "home_region_id"}
    Raises: ValueError if name taken or agent already leads a guild"""

async def join_guild(
    session: AsyncSession, agent_id: int, guild_id: int,
) -> dict:
    """Join a guild as Recruit. Returns: {"guild_id", "rank"}
    Raises: ValueError if already in this guild or guild full"""

async def promote_member(
    session: AsyncSession, leader_agent_id: int, target_agent_id: int, guild_id: int,
    new_rank: str,
) -> dict:
    """Promote a guild member. Only Leader/Officer can promote.
    Returns: {"agent_id", "new_rank"}"""

async def leave_guild(session: AsyncSession, agent_id: int, guild_id: int) -> bool:
    """Leave guild. Leader cannot leave (must transfer or disband). Returns True."""

async def disband_guild(session: AsyncSession, leader_agent_id: int, guild_id: int) -> bool:
    """Disband guild. Only Leader can. Treasury returned to leader. Returns True."""

async def deposit_treasury(
    session: AsyncSession, agent_id: int, guild_id: int, amount: int,
) -> int:
    """Deposit copper into guild treasury. Returns new treasury balance."""

async def get_guild_info(session: AsyncSession, guild_id: int) -> dict:
    """Returns: {"guild_id", "name", "level", "treasury", "home_region",
                 "members": [{"agent_id", "name", "rank"}], "maintenance_cost_per_day"}"""

async def calculate_maintenance(member_count: int) -> int:
    """100 gold + members^1.8 * 10 copper per day.
    Returns daily cost in copper."""

async def collect_maintenance(session: AsyncSession, now: datetime | None = None) -> dict:
    """Deduct daily maintenance from all guild treasuries. Called by housekeeping.
    Guilds that can't pay → is_active = False.
    Returns: {"guilds_charged": int, "guilds_disbanded": int}"""
```

## diplomacy_svc.py

```python
async def get_relationship(
    session: AsyncSession, agent_id: int, target_agent_id: int,
) -> dict:
    """Get relationship between two agents.
    Returns: {"relation_type", "trust_score"}
    Returns neutral if no row exists."""

async def set_relationship(
    session: AsyncSession, agent_id: int, target_agent_id: int,
    relation_type: str, trust_delta: int = 0,
) -> dict:
    """Set relationship type and adjust trust.
    Creates row if not exists. trust_score clamped to [-100, 100].
    Returns: {"relation_type", "trust_score"}"""

async def propose_treaty(
    session: AsyncSession, proposer_agent_id: int, target_agent_id: int | None = None,
    target_guild_id: int | None = None, treaty_type: str = "non_aggression",
    terms: dict | None = None, duration_hours: int = 24,
) -> dict:
    """Propose a treaty. Creates inactive treaty (needs acceptance).
    Returns: {"treaty_id", "treaty_type", "status": "pending"}"""

async def accept_treaty(session: AsyncSession, agent_id: int, treaty_id: int) -> dict:
    """Accept a pending treaty. Sets is_active=True.
    Returns: {"treaty_id", "treaty_type", "status": "active"}"""

async def get_treaties(
    session: AsyncSession, agent_id: int | None = None, guild_id: int | None = None,
    active_only: bool = True,
) -> list[dict]:
    """Get treaties involving an agent or guild."""

async def expire_treaties(session: AsyncSession, now: datetime | None = None) -> int:
    """Expire treaties past their expires_at. Called by housekeeping. Returns count."""
```

## Acceptance Criteria

- [ ] Guild CRUD (create, join, promote, leave, disband)
- [ ] Guild treasury management
- [ ] Maintenance cost calculation and collection
- [ ] Guild disbandment on maintenance failure
- [ ] Agent relationship tracking
- [ ] Treaty proposal and acceptance flow
- [ ] Treaty expiration
- [ ] All amounts in copper

## Dependencies

- **Depends on**: #16 (Foundation), #23 (agent_svc)
- **Blocks**: API routes, game_engine maintenance step
