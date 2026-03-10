## Overview

Implement CLI commands + Alembic migrations for the evolution plan.

## Files

- **Modify**: `src/agentropolis/cli.py`
- **Create**: Alembic migration files
- **Modify**: `src/agentropolis/main.py` (seed_world in lifespan)

## CLI Commands

```python
# python -m agentropolis seed       — seed resources, building types, recipes, skills, world
# python -m agentropolis reset      — drop all data, re-seed
# python -m agentropolis status     — show game state
# python -m agentropolis agents     — list agents
# python -m agentropolis companies  — list companies
# python -m agentropolis regions    — list regions (summary)
# python -m agentropolis sweep      — trigger manual housekeeping sweep
```

## Alembic Migration Order

```
001_regions_skills.py    — Region, RegionConnection, SkillDefinition (no FK deps)
002_agents.py            — Agent, AgentSkill, TravelQueue (depend on Region)
003_company_evolution.py — Modify Company (add founder_agent_id, region_id, npc_* fields)
                           + AgentEmployment + delete Worker
004_guilds_social.py     — Guild, GuildMember, AgentRelationship, Treaty
005_regional_economy.py  — Modify Inventory/Order/Trade/Building/PriceHistory (add region_id etc)
                           + TransportOrder + NpcShop + TaxRecord
006_resource_recipe.py   — Modify Resource (add weight, tier etc) + BuildingType + Recipe (add skills)
007_world_events.py      — WorldEvent + modify GameState (add world_seed, inflation etc)
008_copper_migration.py  — Convert all Numeric columns to BigInteger + data migration
```

## Lifespan Integration

```python
# In main.py lifespan, after seed_game_data:
from agentropolis.services.seed_world import seed_world
async with async_session() as session:
    world_result = await seed_world(session)
    logger.info("World seed: %s", world_result)
```

## Acceptance Criteria

- [ ] All CLI commands working
- [ ] Alembic migrations run in order
- [ ] `alembic upgrade head` creates complete schema
- [ ] World seeded on startup
- [ ] `alembic downgrade` works for each step

## Dependencies

- **Depends on**: #16 (Foundation), #24 (seed_world)
- **Blocks**: None
