## Overview

Implement API endpoints for Skills, Transport, Guild, and Diplomacy.

## Files

- **Create**: `src/agentropolis/api/skills.py`
- **Create**: `src/agentropolis/api/transport.py`
- **Create**: `src/agentropolis/api/guild.py`
- **Create**: `src/agentropolis/api/diplomacy.py`
- **Modify**: `src/agentropolis/main.py` (mount new routers)
- **DO NOT TOUCH**: Other API files, services, models

## api/skills.py

```python
router = APIRouter(prefix="/skills", tags=["skills"])

GET  /api/skills/definitions     → list[SkillDefinitionInfo]
    No auth.

GET  /api/skills/mine            → list[AgentSkillInfo]
    Auth: get_current_agent
```

## api/transport.py

```python
router = APIRouter(prefix="/transport", tags=["transport"])

POST /api/transport/ship         → TransportOrderResponse
    Auth: get_current_agent
    Body: {"items": {"resource_id": qty, ...}, "to_region_id": int,
           "transport_type": str, "use_company": bool (default false)}
    If use_company=True, ships from company inventory, else agent personal

GET  /api/transport/shipments    → list[TransportOrderResponse]
    Auth: get_current_agent
    Query: status=None

GET  /api/transport/routes       → RouteInfoResponse
    Query: from_region_id, to_region_id, weight=0

GET  /api/transport/types        → list[TransportTypeInfo]
    No auth. Returns capacity, speed for each type.
```

## api/guild.py

```python
router = APIRouter(prefix="/guild", tags=["guild"])

POST /api/guild/create           → GuildInfo
    Auth: get_current_agent
    Body: {"name": str}

POST /api/guild/join             → SuccessResponse
    Body: {"guild_id": int}

POST /api/guild/leave            → SuccessResponse
    Body: {"guild_id": int}

POST /api/guild/promote          → SuccessResponse
    Body: {"agent_id": int, "guild_id": int, "rank": str}

POST /api/guild/deposit          → SuccessResponse
    Body: {"guild_id": int, "amount": int}

POST /api/guild/disband          → SuccessResponse
    Body: {"guild_id": int}

GET  /api/guild/{guild_id}       → GuildDetailInfo
GET  /api/guild/list             → list[GuildSummary]
    Query: region_id=None
```

## api/diplomacy.py

```python
router = APIRouter(prefix="/diplomacy", tags=["diplomacy"])

GET  /api/diplomacy/relationships   → list[RelationshipInfo]
    Auth: get_current_agent

POST /api/diplomacy/propose-treaty  → TreatyInfo
    Body: {"target_agent_id": int | None, "target_guild_id": int | None,
           "treaty_type": str, "terms": dict, "duration_hours": int}

POST /api/diplomacy/accept-treaty   → TreatyInfo
    Body: {"treaty_id": int}

GET  /api/diplomacy/treaties        → list[TreatyInfo]
    Auth: get_current_agent
```

## main.py — Mount all new routers

```python
from agentropolis.api.skills import router as skills_router
from agentropolis.api.transport import router as transport_router
from agentropolis.api.guild import router as guild_router
from agentropolis.api.diplomacy import router as diplomacy_router

app.include_router(skills_router, prefix="/api")
app.include_router(transport_router, prefix="/api")
app.include_router(guild_router, prefix="/api")
app.include_router(diplomacy_router, prefix="/api")
```

## Acceptance Criteria

- [ ] All 4 new API files created
- [ ] All endpoints use Agent auth where needed
- [ ] Proper error handling
- [ ] Routers mounted in main.py
- [ ] Session commit after mutations

## Dependencies

- **Depends on**: #16 (Foundation), #25 (skill_svc), #26 (transport+tax+shop), #27 (guild+diplomacy)
- **Blocks**: None
