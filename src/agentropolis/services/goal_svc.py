"""Goal tracking service for autonomy."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.models import (
    Agent,
    AgentGoal,
    AgentSkill,
    AgentTrait,
    Building,
    BuildingType,
    GoalStatus,
    GoalType,
    Inventory,
    Resource,
)
from agentropolis.services import notification_svc
from agentropolis.services.company_svc import get_active_company_model


def _coerce_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _normalize_goal_type(goal_type: str) -> str:
    try:
        return GoalType(goal_type).value
    except ValueError as exc:
        allowed = ", ".join(item.value for item in GoalType)
        raise ValueError(f"Unsupported goal type '{goal_type}'. Allowed: {allowed}") from exc


def _normalize_goal_status(status: str) -> str:
    try:
        return GoalStatus(status).value
    except ValueError as exc:
        allowed = ", ".join(item.value for item in GoalStatus)
        raise ValueError(f"Unsupported goal status '{status}'. Allowed: {allowed}") from exc


def _serialize_goal(goal: AgentGoal) -> dict:
    created_at = goal.__dict__.get("created_at")
    updated_at = goal.__dict__.get("updated_at")
    return {
        "goal_id": goal.id,
        "goal_type": goal.goal_type,
        "status": goal.status,
        "priority": int(goal.priority),
        "target": dict(goal.target or {}),
        "progress": dict(goal.progress or {}),
        "notes": goal.notes,
        "completed_at": _isoformat(goal.completed_at),
        "created_at": _isoformat(created_at),
        "updated_at": _isoformat(updated_at),
    }


async def create_goal(
    session: AsyncSession,
    agent_id: int,
    *,
    goal_type: str,
    priority: int = 100,
    target: dict | None = None,
    notes: str | None = None,
) -> dict:
    goal = AgentGoal(
        agent_id=agent_id,
        goal_type=_normalize_goal_type(goal_type),
        status=GoalStatus.ACTIVE.value,
        priority=int(priority),
        target=dict(target or {}),
        progress={},
        notes=notes,
    )
    session.add(goal)
    await session.flush()
    return _serialize_goal(goal)


async def list_goals(
    session: AsyncSession,
    agent_id: int,
    *,
    include_inactive: bool = True,
) -> list[dict]:
    stmt = (
        select(AgentGoal)
        .where(AgentGoal.agent_id == agent_id)
        .order_by(AgentGoal.status.asc(), AgentGoal.priority.asc(), AgentGoal.id.asc())
    )
    if not include_inactive:
        stmt = stmt.where(AgentGoal.status == GoalStatus.ACTIVE.value)
    result = await session.execute(stmt)
    return [_serialize_goal(goal) for goal in result.scalars().all()]


async def update_goal(
    session: AsyncSession,
    agent_id: int,
    goal_id: int,
    *,
    status: str | None = None,
    priority: int | None = None,
    target: dict | None = None,
    progress: dict | None = None,
    notes: str | None = None,
    now: datetime | None = None,
) -> dict:
    result = await session.execute(
        select(AgentGoal)
        .where(AgentGoal.id == goal_id, AgentGoal.agent_id == agent_id)
        .with_for_update()
    )
    goal = result.scalar_one_or_none()
    if goal is None:
        raise ValueError(f"Goal {goal_id} not found")

    if status is not None:
        normalized_status = _normalize_goal_status(status)
        goal.status = normalized_status
        if normalized_status == GoalStatus.COMPLETED.value:
            goal.completed_at = _coerce_now(now)
        elif normalized_status != GoalStatus.COMPLETED.value:
            goal.completed_at = None
    if priority is not None:
        goal.priority = int(priority)
    if target is not None:
        goal.target = dict(target)
    if progress is not None:
        goal.progress = dict(progress)
    if notes is not None:
        goal.notes = notes

    await session.flush()
    return _serialize_goal(goal)


async def _resource_progress(
    session: AsyncSession,
    agent_id: int,
    goal: AgentGoal,
) -> tuple[dict, bool]:
    ticker = str(goal.target.get("resource", "")).upper().strip()
    target_qty = float(goal.target.get("quantity", 0))
    if not ticker or target_qty <= 0:
        raise ValueError("ACCUMULATE_RESOURCE goal requires target.resource and target.quantity")

    resource = (
        await session.execute(select(Resource).where(Resource.ticker == ticker))
    ).scalar_one_or_none()
    if resource is None:
        raise ValueError(f"Unknown resource ticker: {ticker}")

    agent_qty = float(
        (
            await session.execute(
                select(func.coalesce(func.sum(Inventory.quantity), 0))
                .where(
                    Inventory.agent_id == agent_id,
                    Inventory.company_id.is_(None),
                    Inventory.resource_id == resource.id,
                )
            )
        ).scalar_one()
        or 0
    )

    company_qty = 0.0
    company = await get_active_company_model(session, agent_id)
    if company is not None:
        company_qty = float(
            (
                await session.execute(
                    select(func.coalesce(func.sum(Inventory.quantity), 0))
                    .where(
                        Inventory.company_id == company.id,
                        Inventory.region_id == company.region_id,
                        Inventory.resource_id == resource.id,
                    )
                )
            ).scalar_one()
            or 0
        )

    current = agent_qty + company_qty
    progress = {
        "resource": ticker,
        "current_quantity": round(current, 4),
        "target_quantity": target_qty,
        "agent_quantity": round(agent_qty, 4),
        "company_quantity": round(company_qty, 4),
        "ratio": round(current / target_qty, 4) if target_qty > 0 else 0.0,
    }
    return progress, current >= target_qty


async def _wealth_progress(
    session: AsyncSession,
    agent_id: int,
    goal: AgentGoal,
) -> tuple[dict, bool]:
    target_amount = int(goal.target.get("amount", 0))
    if target_amount <= 0:
        raise ValueError("REACH_WEALTH goal requires target.amount > 0")

    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise ValueError(f"Agent {agent_id} not found")

    company = await get_active_company_model(session, agent_id)
    company_net_worth = float(company.net_worth) if company is not None else 0.0
    current_total = float(agent.personal_balance) + company_net_worth

    progress = {
        "current_total": round(current_total, 2),
        "target_amount": target_amount,
        "agent_balance": int(agent.personal_balance),
        "company_net_worth": round(company_net_worth, 2),
        "ratio": round(current_total / target_amount, 4),
    }
    return progress, current_total >= target_amount


async def _building_progress(
    session: AsyncSession,
    agent_id: int,
    goal: AgentGoal,
) -> tuple[dict, bool]:
    company = await get_active_company_model(session, agent_id)
    if company is None:
        return {"current_count": 0, "required_count": int(goal.target.get("count", 1))}, False

    building_type = str(goal.target.get("building_type", "")).strip()
    required_count = int(goal.target.get("count", 1))
    if required_count <= 0:
        required_count = 1

    stmt = select(func.count(Building.id)).where(Building.company_id == company.id)
    if building_type:
        stmt = (
            select(func.count(Building.id))
            .join(BuildingType, BuildingType.id == Building.building_type_id)
            .where(
                Building.company_id == company.id,
                BuildingType.name == building_type,
            )
        )
    current_count = int((await session.execute(stmt)).scalar_one() or 0)
    progress = {
        "building_type": building_type or None,
        "current_count": current_count,
        "required_count": required_count,
        "ratio": round(current_count / required_count, 4),
    }
    return progress, current_count >= required_count


async def _skill_progress(
    session: AsyncSession,
    agent_id: int,
    goal: AgentGoal,
) -> tuple[dict, bool]:
    skill_name = str(goal.target.get("skill_name", "")).strip()
    target_level = int(goal.target.get("level", 0))
    if not skill_name or target_level <= 0:
        raise ValueError("REACH_SKILL_LEVEL goal requires target.skill_name and target.level")

    skill = (
        await session.execute(
            select(AgentSkill).where(
                AgentSkill.agent_id == agent_id,
                AgentSkill.skill_name == skill_name,
            )
        )
    ).scalar_one_or_none()
    current_level = int(skill.level) if skill is not None else 0
    progress = {
        "skill_name": skill_name,
        "current_level": current_level,
        "target_level": target_level,
        "ratio": round(current_level / target_level, 4),
    }
    return progress, current_level >= target_level


async def _region_progress(
    session: AsyncSession,
    agent_id: int,
    goal: AgentGoal,
) -> tuple[dict, bool]:
    target_region_id = int(goal.target.get("region_id", 0))
    if target_region_id <= 0:
        raise ValueError("REACH_REGION goal requires target.region_id")

    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise ValueError(f"Agent {agent_id} not found")

    progress = {
        "current_region_id": agent.current_region_id,
        "target_region_id": target_region_id,
        "reached": agent.current_region_id == target_region_id,
    }
    return progress, agent.current_region_id == target_region_id


async def _trait_progress(
    session: AsyncSession,
    agent_id: int,
    goal: AgentGoal,
) -> tuple[dict, bool]:
    trait_id = str(goal.target.get("trait_id", "")).strip()
    if not trait_id:
        raise ValueError("EARN_TRAIT goal requires target.trait_id")

    trait = (
        await session.execute(
            select(AgentTrait).where(
                AgentTrait.agent_id == agent_id,
                AgentTrait.trait_id == trait_id,
            )
        )
    ).scalar_one_or_none()
    progress = {
        "trait_id": trait_id,
        "earned": trait is not None,
        "tier": trait.tier.name if trait is not None else None,
    }
    return progress, trait is not None


async def compute_goal_progress(
    session: AsyncSession,
    goal: AgentGoal,
    *,
    now: datetime | None = None,
) -> dict:
    timestamp = _coerce_now(now)
    completed = False
    if goal.goal_type == GoalType.ACCUMULATE_RESOURCE.value:
        progress, completed = await _resource_progress(session, goal.agent_id, goal)
    elif goal.goal_type == GoalType.REACH_WEALTH.value:
        progress, completed = await _wealth_progress(session, goal.agent_id, goal)
    elif goal.goal_type == GoalType.BUILD_BUILDING.value:
        progress, completed = await _building_progress(session, goal.agent_id, goal)
    elif goal.goal_type == GoalType.REACH_SKILL_LEVEL.value:
        progress, completed = await _skill_progress(session, goal.agent_id, goal)
    elif goal.goal_type == GoalType.REACH_REGION.value:
        progress, completed = await _region_progress(session, goal.agent_id, goal)
    elif goal.goal_type == GoalType.EARN_TRAIT.value:
        progress, completed = await _trait_progress(session, goal.agent_id, goal)
    else:
        progress = dict(goal.progress or {})
        completed = goal.status == GoalStatus.COMPLETED.value

    goal.progress = progress
    if completed and goal.status != GoalStatus.COMPLETED.value:
        goal.status = GoalStatus.COMPLETED.value
        goal.completed_at = timestamp
        await notification_svc.notify(
            session,
            goal.agent_id,
            "goal_completed",
            "Goal completed",
            f"{goal.goal_type} completed",
            data={"goal_id": goal.id, "goal_type": goal.goal_type},
        )
    elif not completed and goal.status == GoalStatus.COMPLETED.value:
        goal.status = GoalStatus.ACTIVE.value
        goal.completed_at = None

    await session.flush()
    return _serialize_goal(goal)


async def compute_all_goal_progress(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict:
    timestamp = _coerce_now(now)
    result = await session.execute(
        select(AgentGoal)
        .where(AgentGoal.status.in_((GoalStatus.ACTIVE.value, GoalStatus.COMPLETED.value)))
        .order_by(AgentGoal.agent_id.asc(), AgentGoal.priority.asc(), AgentGoal.id.asc())
    )
    goals = list(result.scalars().all())

    completed_now = 0
    for goal in goals:
        before_status = goal.status
        await compute_goal_progress(session, goal, now=timestamp)
        if before_status != GoalStatus.COMPLETED.value and goal.status == GoalStatus.COMPLETED.value:
            completed_now += 1

    return {
        "goals_processed": len(goals),
        "completed_now": completed_now,
    }
