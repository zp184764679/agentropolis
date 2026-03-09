"""Reputation effects service.

Agent reputation affects:
- NPC shop prices (discount/premium)
- Access to NPC shops (banned below threshold)
- Contract trustworthiness
"""

from agentropolis.config import settings


def get_reputation_modifier(reputation: float) -> float:
    """Get price modifier based on reputation.

    Positive reputation = discount (< 1.0)
    Negative reputation = premium (> 1.0)
    Range: 0.9 to 1.2
    """
    # Linear interpolation: rep -100 → 1.2, rep 0 → 1.0, rep +100 → 0.9
    if reputation >= 0:
        return 1.0 - (reputation / 100.0) * 0.1  # max 10% discount
    else:
        return 1.0 - (reputation / 100.0) * 0.2  # max 20% premium


def check_shop_access(reputation: float) -> bool:
    """Check if an agent can access NPC shops.

    Returns: True if allowed, False if reputation too low
    """
    return reputation >= settings.REPUTATION_SHOP_BAN_THRESHOLD


async def adjust_reputation(
    session,
    agent_id: int,
    delta: float,
    reason: str = "",
) -> float:
    """Adjust an agent's reputation. Clamps to [-100, 100].

    Returns: new reputation value
    """
    from sqlalchemy import select

    from agentropolis.models.agent import Agent

    result = await session.execute(
        select(Agent).where(Agent.id == agent_id).with_for_update()
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise ValueError(f"Agent {agent_id} not found")

    agent.reputation = max(-100.0, min(100.0, agent.reputation + delta))
    await session.flush()

    return agent.reputation
