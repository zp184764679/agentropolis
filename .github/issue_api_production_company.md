## Overview

Update Production + Company API endpoints for the evolution plan.

## Files

- **Modify**: `src/agentropolis/api/production.py`
- **Modify**: `src/agentropolis/api/company.py`
- **DO NOT TOUCH**: Other API files, services, models

## api/company.py Changes

```python
# Registration moves to /api/agent/register (Agent API)
# Company creation is now POST /api/agent/create-company (Agent API)
# This file focuses on company management

router = APIRouter(prefix="/company", tags=["company"])

GET  /api/company/status         → CompanyStatus
    Auth: get_current_agent → resolve company
    Calls: company_svc.get_company_status()

GET  /api/company/workers        → NpcWorkerInfo
    Auth: get_current_agent → resolve company
    Returns: npc_worker_count, npc_satisfaction, consumption rates, productivity_modifier

GET  /api/company/employees      → list[EmploymentInfo]
    Auth: get_current_agent → resolve company
    Returns: list of AgentEmployments for this company

POST /api/company/hire           → EmploymentInfo
    Auth: get_current_agent → resolve company (must be CEO/Director)
    Body: {"agent_id": int, "role": str, "salary_per_second": int}

POST /api/company/fire           → SuccessResponse
    Body: {"agent_id": int}
```

## api/production.py Changes

```python
router = APIRouter(prefix="/production", tags=["production"])

GET  /api/production/buildings    → list[BuildingInfo]
    Auth: get_current_agent → resolve company
    Calls: production.get_company_buildings()

GET  /api/production/recipes?building_type=X → list[RecipeInfo]
    No auth needed.
    Includes: required_skill, min_skill_level, skill_xp_reward

GET  /api/production/building-types → list[BuildingTypeInfo]
    No auth needed.
    Includes: required_skill, min_skill_level

POST /api/production/start       → SuccessResponse
    Auth: get_current_agent → resolve company
    Body: {"building_id": int, "recipe_id": int}
    Validates agent skill requirements

POST /api/production/stop        → SuccessResponse
    Body: {"building_id": int}

POST /api/production/build       → SuccessResponse
    Body: {"building_type": str}
    Validates agent skill requirements
```

## NpcWorkerInfo Schema

```python
class NpcWorkerInfo(BaseModel):
    npc_worker_count: int
    npc_satisfaction: float
    rat_consumption_per_hour: int  # copper value
    dw_consumption_per_hour: int
    productivity_modifier: float  # 1.0 or 0.5
```

## Company Resolution Pattern

```python
async def resolve_company(session: AsyncSession, agent: Agent) -> Company:
    """Get agent's company in their current region."""
    result = await session.execute(
        select(Company).where(
            Company.founder_agent_id == agent.id,
            Company.region_id == agent.current_region_id,
            Company.is_active.is_(True)
        )
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(400, "No active company in current region")
    return company
```

## Acceptance Criteria

- [ ] All endpoints use Agent auth
- [ ] Company resolved from agent context
- [ ] NPC worker info (replaces old Worker endpoint)
- [ ] Employee management (hire/fire)
- [ ] Skill requirements shown in recipes/building types
- [ ] Integer amounts

## Dependencies

- **Depends on**: #16 (Foundation), #18 (company_svc), #20 (production)
- **Blocks**: None
