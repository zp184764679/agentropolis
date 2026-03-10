"""Skills REST API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentropolis.api.auth import get_current_agent
from agentropolis.api.preview_guard import (
    make_agent_preview_access_guard,
    require_preview_surface,
)
from agentropolis.api.schemas import AgentSkillInfo, SkillInfo
from agentropolis.database import get_session
from agentropolis.models import Agent
from agentropolis.services.skill_svc import (
    get_agent_skills,
    get_all_skill_definitions,
)

router = APIRouter(
    prefix="/skills",
    tags=["skills"],
    dependencies=[Depends(require_preview_surface)],
)
skills_access_guard = make_agent_preview_access_guard("strategy")


@router.get("/definitions", response_model=list[SkillInfo])
async def get_skill_definitions(session: AsyncSession = Depends(get_session)):
    """Get all available skill definitions."""
    return await get_all_skill_definitions(session)


@router.get("/mine", response_model=list[AgentSkillInfo])
async def get_my_skills(
    _guard: None = Depends(skills_access_guard),
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session),
):
    """Get your agent's skills and XP."""
    return await get_agent_skills(session, agent.id)
