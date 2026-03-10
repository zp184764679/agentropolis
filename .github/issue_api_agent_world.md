## Overview

Implement Agent + World REST API endpoints.

## Files

- **Create**: `src/agentropolis/api/agent.py`
- **Create**: `src/agentropolis/api/world.py`
- **Modify**: `src/agentropolis/main.py` (mount new routers)
- **DO NOT TOUCH**: Other API files, services, models

## api/agent.py — Agent Endpoints

```python
router = APIRouter(prefix="/agent", tags=["agent"])

POST /api/agent/register         → AgentRegisterResponse
    Body: {"name": str}
    No auth required.
    Calls: agent_svc.register_agent()

GET  /api/agent/status           → AgentStatus
    Auth: get_current_agent
    Calls: agent_svc.get_agent_status()

POST /api/agent/eat              → SuccessResponse
    Auth: get_current_agent
    Body: {"resource_id": int, "quantity": int}
    Calls: agent_svc.eat()

POST /api/agent/drink            → SuccessResponse
    Auth: get_current_agent
    Body: {"resource_id": int, "quantity": int}
    Calls: agent_svc.drink()

POST /api/agent/rest             → SuccessResponse
    Auth: get_current_agent
    Body: {"duration_seconds": int}
    Calls: agent_svc.rest()

POST /api/agent/travel           → TravelStatusResponse
    Auth: get_current_agent
    Body: {"to_region_id": int}
    Calls: world_svc.start_travel()

GET  /api/agent/travel/status    → TravelStatusResponse | null
    Auth: get_current_agent
    Calls: world_svc.get_travel_status()

POST /api/agent/create-company   → CompanyCreateResponse
    Auth: get_current_agent
    Body: {"name": str}
    Calls: company_svc.register_company(agent_id, agent.current_region_id, name)

POST /api/agent/respawn          → AgentStatus
    Auth: get_current_agent
    Calls: agent_svc.respawn()

GET  /api/agent/skills           → list[AgentSkillInfo]
    Auth: get_current_agent
    Calls: skill_svc.get_agent_skills()
```

## api/world.py — World Endpoints

```python
router = APIRouter(prefix="/world", tags=["world"])

GET  /api/world/regions          → list[RegionSummary]
    No auth required.
    Calls: world_svc.get_all_regions()

GET  /api/world/region/{id}      → RegionDetail
    No auth required.
    Calls: world_svc.get_region()

GET  /api/world/map              → WorldMapResponse
    No auth required.
    Calls: world_svc.get_world_map()

GET  /api/world/route            → RouteInfoResponse
    Query params: from_region_id, to_region_id
    Calls: world_svc.find_path()

GET  /api/world/events           → list[WorldEventInfo]
    Query params: region_id (optional)
    Calls: event_svc.get_active_events()
```

## Error Handling Pattern

```python
@router.post("/eat")
async def eat(
    req: EatRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    try:
        result = await agent_svc.eat(session, agent.id, req.resource_id, req.quantity)
        await session.commit()
        return SuccessResponse(message=f"Consumed {result['consumed']} units. Hunger: {result['hunger']:.0f}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

## Schemas Needed (in schemas.py — already created by #16)

- `AgentRegisterRequest(name: str)`
- `AgentRegisterResponse(agent_id, name, api_key, home_region_id, balance)`
- `AgentStatus(agent_id, name, health, hunger, thirst, energy, ...)`
- `EatRequest(resource_id: int, quantity: int)`
- `DrinkRequest(resource_id: int, quantity: int)`
- `RestRequest(duration_seconds: int)`
- `TravelRequest(to_region_id: int)`
- `TravelStatusResponse(from_region, to_region, progress_pct, ...)`
- `CreateCompanyRequest(name: str)`
- `RegionSummary(region_id, name, safety_tier, region_type)`
- `RegionDetail(... + connections, companies_count, agents_count)`
- `WorldMapResponse(regions, connections)`
- `RouteInfoResponse(path, total_time, cost)`

## main.py Changes

```python
from agentropolis.api.agent import router as agent_router
from agentropolis.api.world import router as world_router

app.include_router(agent_router, prefix="/api")
app.include_router(world_router, prefix="/api")
```

## Acceptance Criteria

- [ ] All agent endpoints working
- [ ] All world endpoints working
- [ ] Proper auth (get_current_agent) on protected endpoints
- [ ] Error handling with HTTPException
- [ ] Services called correctly
- [ ] Session commit after mutations
- [ ] Routers mounted in main.py

## Dependencies

- **Depends on**: #16 (Foundation), #23 (agent_svc), #24 (world_svc), #25 (skill_svc)
- **Blocks**: None
