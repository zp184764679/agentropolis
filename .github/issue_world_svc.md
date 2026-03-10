## Overview

Implement World service + seed_world — region queries, pathfinding, travel, and procedural generation of 80+ regions.

## Files

- **Create**: `src/agentropolis/services/world_svc.py`
- **Create**: `src/agentropolis/services/seed_world.py`
- **DO NOT TOUCH**: Model files, other services

## world_svc.py — Region Queries + Pathfinding + Travel

```python
async def get_region(session: AsyncSession, region_id: int) -> dict:
    """Get region details.
    Returns: {"region_id", "name", "safety_tier", "region_type",
              "price_coefficient", "tax_rate", "treasury",
              "resource_specializations", "description",
              "connections": [{"to_region_id", "to_name", "travel_time_seconds",
                               "terrain_type", "is_portal", "danger_level"}],
              "companies_count", "agents_count", "npc_shops": [...]}"""

async def get_all_regions(session: AsyncSession) -> list[dict]:
    """Get all regions (summary). Returns: [{"region_id", "name", "safety_tier",
    "region_type", "connections_count"}]"""

async def get_world_map(session: AsyncSession) -> dict:
    """Get full graph for client rendering.
    Returns: {"regions": [{"id", "name", "safety_tier", "type"}],
              "connections": [{"from", "to", "time", "portal"}]}"""

async def find_path(
    session: AsyncSession, from_region_id: int, to_region_id: int,
) -> dict:
    """Dijkstra shortest path.
    Returns: {"path": [region_id, ...], "total_time_seconds": int,
              "total_danger": int, "connections": [...]}
    Raises: ValueError if no path exists"""

async def start_travel(
    session: AsyncSession, agent_id: int, to_region_id: int,
    now: datetime | None = None,
) -> dict:
    """Start agent travel to destination.
    1. Check agent not already traveling (TravelQueue)
    2. Check agent is alive
    3. Find path from current_region to to_region
    4. Calculate total travel time
    5. Insert TravelQueue row (departed_at=now, arrives_at=now+time)
    Returns: {"from_region", "to_region", "departed_at", "arrives_at",
              "travel_time_seconds", "path": [...]}
    Raises: ValueError if already traveling, dead, or no path"""

async def settle_travel(
    session: AsyncSession, agent_id: int, now: datetime | None = None,
) -> dict | None:
    """Check if agent has arrived. If arrives_at <= now:
    1. Update agent.current_region_id = to_region_id
    2. Delete TravelQueue row
    3. Return arrival info
    If not arrived yet, return None."""

async def get_travel_status(session: AsyncSession, agent_id: int) -> dict | None:
    """Get current travel status. None if not traveling.
    Returns: {"from_region", "to_region", "departed_at", "arrives_at",
              "remaining_seconds", "progress_pct"}"""
```

## seed_world.py — Procedural World Generation

```python
async def seed_world(session: AsyncSession) -> dict:
    """Generate 80+ regions with star topology. Idempotent.

    Structure:
    - 4 Capital Hubs (CORE safety, CAPITAL type)
    - Each hub connects to 4-6 Towns (CORE/BORDER safety)
    - Each town connects to 2-4 Villages (BORDER/RESOURCE safety)
    - Villages connect to 1-2 Outposts (RESOURCE/WILDERNESS safety)
    - 4 Portal connections between Capital Hubs (instant but expensive)

    Naming: Use thematic names (e.g., "Ironforge", "Crystalport", "Darkwood Outpost")
    Resource specializations: Each region gets 2-3 resources with 1.5x-3.0x multipliers
    Tax rates: Core=3%, Border=5%, Resource=7%, Wilderness=10%
    Travel times: Hub↔Town=120s, Town↔Village=180s, Village↔Outpost=300s, Portal=10s

    Returns: {"regions_created": int, "connections_created": int}"""
```

## Dijkstra Implementation

```python
import heapq

def dijkstra(graph: dict[int, list[tuple[int, int]]], start: int, end: int):
    """graph = {region_id: [(neighbor_id, travel_time), ...]}
    Returns (path: list[int], total_time: int) or raises ValueError"""
    dist = {start: 0}
    prev = {}
    pq = [(0, start)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == end:
            path = []
            while u is not None:
                path.append(u)
                u = prev.get(u)
            return list(reversed(path)), d
        if d > dist.get(u, float('inf')):
            continue
        for v, w in graph.get(u, []):
            nd = d + w
            if nd < dist.get(v, float('inf')):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    raise ValueError(f"No path from {start} to {end}")
```

## World Generation Topology

```
            [Capital-North]
           / |  |  \
      Town1 Town2 Town3 Town4
      /  \    |     |    \
   Vil1 Vil2 Vil3  Vil4  Vil5
    |         |           |
   Out1      Out2        Out3

 Portal ←→ [Capital-East] ←→ Portal
            [Capital-South]
            [Capital-West]

(Each capital has similar sub-tree)
(Portals connect all 4 capitals to each other)
```

## Region Name Themes

- Capital: grand names ("Ironhold", "Crystalport", "Shadowhaven", "Sunreach")
- Towns: functional ("Millbrook", "Copperdale", "Fishmarket", "Stonequarry")
- Villages: descriptive ("Pine Hollow", "Red Clay", "Windswept Ridge")
- Outposts: frontier ("Darkwood Outpost", "Frozen Watch", "Lost Mine")
- Wilderness: dangerous ("Bandit's Pass", "Dragon's Teeth", "The Blighted Wastes")

## Acceptance Criteria

- [ ] 80+ regions generated with correct topology
- [ ] Star topology with 4 capital hubs
- [ ] Portal connections between capitals
- [ ] Safety tiers assigned by distance from center
- [ ] Resource specializations per region
- [ ] Dijkstra pathfinding works
- [ ] Travel start/settle/status works
- [ ] Idempotent seed (safe to run multiple times)
- [ ] Thematic region names

## Dependencies

- **Depends on**: #16 (Foundation)
- **Blocks**: API routes, game_engine transport step
