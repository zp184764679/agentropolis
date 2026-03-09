"""FastAPI application entry point.

- Mounts all REST API routers
- Starts tick loop in lifespan
- Mounts MCP server at /mcp
- Seeds game data on first run
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agentropolis.api.company import router as company_router
from agentropolis.api.game import router as game_router
from agentropolis.api.inventory import router as inventory_router
from agentropolis.api.market import router as market_router
from agentropolis.api.production import router as production_router
from agentropolis.config import settings
from agentropolis.database import async_session, engine
from agentropolis.services.seed import seed_game_data

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: seed data, start tick loop."""
    # Seed game data
    async with async_session() as session:
        result = await seed_game_data(session)
        logger.info("Seed complete: %s", result)

    # TODO (Issue #6): Start tick loop
    # task = asyncio.create_task(run_tick_loop())

    yield

    # TODO (Issue #6): Cancel tick loop
    # task.cancel()

    await engine.dispose()


app = FastAPI(
    title="Agentropolis",
    description="AI Agent Economic Arena - competitive economy simulation for AI Agents",
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

# Mount REST API routers
app.include_router(market_router, prefix="/api")
app.include_router(production_router, prefix="/api")
app.include_router(inventory_router, prefix="/api")
app.include_router(company_router, prefix="/api")
app.include_router(game_router, prefix="/api")

# TODO (Issue #13): Mount MCP server
# from agentropolis.mcp.server import mcp
# app.mount("/mcp", mcp.sse_app())


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
