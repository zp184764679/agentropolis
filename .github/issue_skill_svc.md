## Overview

Implement Skill service — skill definitions, XP tracking, level-up, and efficiency bonuses.

19 skills across 4 categories. Agents gain XP by completing recipes. Each level gives +20% efficiency.

## Files

- **Create**: `src/agentropolis/services/skill_svc.py`
- **Modify**: `src/agentropolis/services/seed.py` (add skill definition seed data)
- **DO NOT TOUCH**: Model files, other services

## skill_svc.py

```python
async def get_skill_definitions(session: AsyncSession) -> list[dict]:
    """Get all skill definitions.
    Returns: [{"name", "category", "description", "prerequisites", "xp_per_level"}]"""

async def get_agent_skills(session: AsyncSession, agent_id: int) -> list[dict]:
    """Get all skills for an agent.
    Returns: [{"skill_name", "level", "xp", "xp_to_next", "efficiency_bonus"}]"""

async def add_xp(
    session: AsyncSession, agent_id: int, skill_name: str, xp_amount: int,
    now: datetime | None = None,
) -> dict:
    """Add XP to an agent's skill. Creates AgentSkill row if not exists.
    Auto-levels up if XP threshold reached.
    Returns: {"skill_name", "level", "xp", "leveled_up": bool, "new_level": int | None}"""

async def check_skill_requirement(
    session: AsyncSession, agent_id: int, skill_name: str, min_level: int,
) -> bool:
    """Check if agent meets a skill requirement. Returns True/False."""

async def get_efficiency_bonus(
    session: AsyncSession, agent_id: int, skill_name: str,
) -> float:
    """Get efficiency multiplier for a skill.
    Level 0 (no skill): 1.0
    Level 1: 1.0, Level 2: 1.2, Level 3: 1.4, Level 4: 1.6, Level 5: 1.8
    Formula: 1.0 + max(0, (level - 1)) * 0.2"""
```

## Skill Definitions (seed data for seed.py)

```python
SKILL_DEFINITIONS = [
    # Gathering
    {"name": "Mining", "category": "gathering", "description": "Extract ores and minerals"},
    {"name": "Logging", "category": "gathering", "description": "Harvest wood resources"},
    {"name": "Herbalism", "category": "gathering", "description": "Gather herbs and plants"},
    {"name": "Hunting", "category": "gathering", "description": "Hunt animals for resources"},
    {"name": "Fishing", "category": "gathering", "description": "Catch fish from water"},
    # Crafting
    {"name": "Smelting", "category": "crafting", "description": "Smelt ores into ingots"},
    {"name": "Smithing", "category": "crafting", "description": "Forge metals into equipment"},
    {"name": "Tailoring", "category": "crafting", "description": "Craft cloth and leather items"},
    {"name": "Alchemy", "category": "crafting", "description": "Brew potions and reagents"},
    {"name": "Cooking", "category": "crafting", "description": "Prepare food and rations"},
    {"name": "Engineering", "category": "crafting", "description": "Build machinery and devices"},
    # Commerce
    {"name": "Trading", "category": "commerce", "description": "Better market prices"},
    {"name": "Appraisal", "category": "commerce", "description": "Identify item values"},
    {"name": "Logistics", "category": "commerce", "description": "Reduce transport costs"},
    {"name": "Negotiation", "category": "commerce", "description": "Better NPC deals"},
    # Social
    {"name": "Leadership", "category": "social", "description": "Manage larger teams"},
    {"name": "Diplomacy", "category": "social", "description": "Better treaty terms"},
    {"name": "Espionage", "category": "social", "description": "Gather intelligence"},
    {"name": "Management", "category": "social", "description": "Improve company efficiency"},
]

# XP thresholds (same for all skills)
XP_PER_LEVEL = {"1": 0, "2": 100, "3": 400, "4": 1600, "5": 6400}
# Total XP needed: 0 → 100 → 400 → 1600 → 6400 (x4 progression)
```

## Level-Up Logic

```python
def check_level_up(current_level: int, current_xp: int, xp_thresholds: dict) -> int:
    """Return new level after XP gain."""
    for lvl in range(5, current_level, -1):  # check highest first
        if current_xp >= xp_thresholds[str(lvl)]:
            return lvl
    return current_level
```

## Acceptance Criteria

- [ ] 19 skill definitions seeded
- [ ] XP tracking per agent per skill
- [ ] Auto-level-up when threshold reached
- [ ] Efficiency bonus calculation (level-based)
- [ ] Skill requirement check
- [ ] Seed is idempotent
- [ ] AgentSkill row created on first XP gain

## Dependencies

- **Depends on**: #16 (Foundation)
- **Blocks**: #20 (production uses skill checks), API routes
