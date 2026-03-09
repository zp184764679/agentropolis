"""Treaty mechanical effects service.

Translates treaty types into gameplay effects:
- TRADE_AGREEMENT → trade tax reduced by 50% between parties
- NON_AGGRESSION → blocks warfare contracts between parties
- MUTUAL_DEFENSE → auto-creates defense contract when ally attacked
- ALLIANCE → all of the above
"""

import logging

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.models.treaty import Treaty

logger = logging.getLogger(__name__)


async def get_treaty_between(
    session: AsyncSession,
    agent_a_id: int,
    agent_b_id: int,
) -> list[dict]:
    """Get all active treaties between two agents.

    Returns: [{"treaty_id", "treaty_type", "effects"}]
    """
    result = await session.execute(
        select(Treaty).where(
            Treaty.is_active == True,  # noqa: E712
            or_(
                (Treaty.party_a_agent_id == agent_a_id) & (Treaty.party_b_agent_id == agent_b_id),
                (Treaty.party_a_agent_id == agent_b_id) & (Treaty.party_b_agent_id == agent_a_id),
            ),
        )
    )
    treaties = result.scalars().all()

    return [
        {
            "treaty_id": t.id,
            "treaty_type": t.treaty_type.value if hasattr(t.treaty_type, 'value') else str(t.treaty_type),
            "effects": _get_effects_for_type(t.treaty_type),
        }
        for t in treaties
    ]


def _get_effects_for_type(treaty_type) -> dict[str, str]:
    """Get effects description for a treaty type."""
    tt = treaty_type.value if hasattr(treaty_type, 'value') else str(treaty_type)

    effects_map = {
        "trade_agreement": {
            "trade_tax": "50% reduction between parties",
        },
        "non_aggression": {
            "warfare": "blocks warfare contracts between parties",
        },
        "mutual_defense": {
            "warfare": "blocks warfare contracts between parties",
            "defense": "auto-creates defense contract when ally attacked",
        },
        "alliance": {
            "trade_tax": "50% reduction between parties",
            "warfare": "blocks warfare contracts between parties",
            "defense": "auto-creates defense contract when ally attacked",
        },
    }
    return effects_map.get(tt, {})


def get_trade_tax_modifier(treaties: list[dict]) -> float:
    """Get trade tax modifier from active treaties.

    Returns: multiplier (0.5 if trade agreement, 1.0 otherwise)
    """
    for t in treaties:
        tt = t.get("treaty_type", "")
        if tt in ("trade_agreement", "alliance"):
            return 0.5
    return 1.0


def check_warfare_blocked(treaties: list[dict]) -> bool:
    """Check if warfare is blocked by a treaty.

    Returns: True if warfare is blocked
    """
    for t in treaties:
        tt = t.get("treaty_type", "")
        if tt in ("non_aggression", "mutual_defense", "alliance"):
            return True
    return False


def check_mutual_defense(treaties: list[dict]) -> bool:
    """Check if mutual defense applies.

    Returns: True if mutual defense or alliance exists
    """
    for t in treaties:
        tt = t.get("treaty_type", "")
        if tt in ("mutual_defense", "alliance"):
            return True
    return False
