"""FastAPI application entry point.

Current runtime role:
- mount the currently wired REST scaffold routers
- seed scaffold game data on startup
- expose a minimal health endpoint

Target runtime direction:
- start housekeeping/background orchestration in lifespan
- mount the stabilized MCP surface once the control contract is frozen
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agentropolis.api.agent import router as agent_router
from agentropolis.api.company import router as company_router
from agentropolis.api.control_plane import router as control_plane_router
from agentropolis.api.diplomacy import router as diplomacy_router
from agentropolis.api.decisions import router as decisions_router
from agentropolis.api.game import router as game_router
from agentropolis.api.guild import router as guild_router
from agentropolis.api.inventory import router as inventory_router
from agentropolis.api.market import router as market_router
from agentropolis.api.production import router as production_router
from agentropolis.api.skills import router as skills_router
from agentropolis.api.strategy import router as strategy_router
from agentropolis.api.transport import router as transport_router
from agentropolis.api.warfare import router as warfare_router
from agentropolis.api.world import router as world_router
from agentropolis.config import settings
from agentropolis.database import async_session, engine
from agentropolis.runtime_meta import build_runtime_metadata
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: seed initial data and manage long-lived runtime hooks."""
    # Seed game data
    async with async_session() as session:
        resource_result = await seed_game_data(session)
        world_result = await seed_world(session)
        logger.info("Seed complete: resources=%s world=%s", resource_result, world_result)

    # TODO: replace the legacy tick-loop stub with housekeeping/background orchestration.
    # task = asyncio.create_task(run_housekeeping_loop())

    yield

    # TODO: cancel the housekeeping/background task on shutdown.
    # task.cancel()

    await engine.dispose()


app = FastAPI(
    title="Agentropolis",
    description="AI-native simulated world and control plane for LLM agents",
    version="0.1.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the current scaffold surface plus the target agent-auth preview surface.
# These target routers are service-backed now, but they are still preview APIs:
# public contract freeze, rollout gating, and MCP parity remain future work.
app.include_router(market_router, prefix="/api")
app.include_router(production_router, prefix="/api")
app.include_router(inventory_router, prefix="/api")
app.include_router(company_router, prefix="/api")
app.include_router(game_router, prefix="/api")
app.include_router(control_plane_router)
app.include_router(agent_router, prefix="/api")
app.include_router(world_router, prefix="/api")
app.include_router(skills_router, prefix="/api")
app.include_router(transport_router, prefix="/api")
app.include_router(guild_router, prefix="/api")
app.include_router(diplomacy_router, prefix="/api")
app.include_router(strategy_router, prefix="/api")
app.include_router(decisions_router, prefix="/api")
app.include_router(warfare_router, prefix="/api")

# TODO: mount the MCP surface after the transport and external contract are frozen.
# from agentropolis.mcp.server import mcp
# app.mount("/mcp", mcp.sse_app())


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/meta/runtime")
async def runtime_metadata():
    """Machine-readable snapshot of the current scaffold/runtime surface."""
    return build_runtime_metadata()


@app.exception_handler(NotImplementedError)
async def handle_not_implemented(_: Request, exc: NotImplementedError):
    """Expose scaffold placeholders as HTTP 501 instead of generic 500s."""
    return JSONResponse(
        status_code=501,
        content={
            "detail": str(exc) or "This scaffold endpoint is not implemented yet.",
            "status": "not_implemented",
        },
    )
