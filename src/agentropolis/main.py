"""FastAPI application entry point.

Current runtime role:
- mount the currently wired REST scaffold routers
- seed scaffold game data on startup
- expose a minimal health endpoint

Target runtime direction:
- start housekeeping/background orchestration in lifespan when enabled
- mount the local-preview MCP core surface only when explicitly enabled
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agentropolis.api.agent import router as agent_router
from agentropolis.api.alerts import router as alerts_router
from agentropolis.api.autonomy import router as autonomy_router
from agentropolis.api.company import router as company_router
from agentropolis.api.contract import router as contract_router
from agentropolis.api.control_plane import router as control_plane_router
from agentropolis.api.dashboard import router as dashboard_router
from agentropolis.api.digest import router as digest_router
from agentropolis.api.diplomacy import router as diplomacy_router
from agentropolis.api.decisions import router as decisions_router
from agentropolis.api.execution import router as execution_router
from agentropolis.api.game import router as game_router
from agentropolis.api.guild import router as guild_router
from agentropolis.api.inventory import router as inventory_router
from agentropolis.api.market_analysis import router as market_analysis_router
from agentropolis.api.market import router as market_router
from agentropolis.api.observability import router as observability_router
from agentropolis.api.production import router as production_router
from agentropolis.api.rollout_readiness import router as rollout_readiness_router
from agentropolis.api.skills import router as skills_router
from agentropolis.api.strategy import router as strategy_router
from agentropolis.api.transport import router as transport_router
from agentropolis.api.warfare import router as warfare_router
from agentropolis.api.world import router as world_router
from agentropolis.api.preview_guard import (
    ERROR_CODE_HEADER,
    get_preview_guard_state,
)
from agentropolis.config import settings
from agentropolis.database import async_session, engine, get_session
from agentropolis.middleware import (
    REQUEST_ID_HEADER,
    RequestConcurrencyMiddleware,
    RequestContextMiddleware,
    RequestMetricsMiddleware,
)
from agentropolis.runtime_meta import build_runtime_metadata
from agentropolis.services.game_engine import run_tick_loop
from agentropolis.services.seed import seed_game_data
from agentropolis.services.seed_world import seed_world
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: seed initial data and manage long-lived runtime hooks."""
    housekeeping_stop: asyncio.Event | None = None
    housekeeping_task: asyncio.Task | None = None

    # Seed game data
    async with async_session() as session:
        resource_result = await seed_game_data(session)
        world_result = await seed_world(session)
        logger.info("Seed complete: resources=%s world=%s", resource_result, world_result)

    if settings.HOUSEKEEPING_AUTOSTART:
        housekeeping_stop = asyncio.Event()
        housekeeping_task = asyncio.create_task(run_tick_loop(housekeeping_stop))
        logger.info("Housekeeping loop started")

    yield

    if housekeeping_stop is not None:
        housekeeping_stop.set()
    if housekeeping_task is not None:
        housekeeping_task.cancel()
        try:
            await housekeeping_task
        except asyncio.CancelledError:
            pass

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
app.add_middleware(RequestConcurrencyMiddleware)
app.add_middleware(RequestMetricsMiddleware)
app.add_middleware(RequestContextMiddleware)

# Mount the current scaffold surface plus the target agent-auth preview surface.
# These target routers are service-backed now, but they are still preview APIs:
# public contract freeze, rollout gating, and MCP parity remain future work.
app.include_router(market_router, prefix="/api")
app.include_router(production_router, prefix="/api")
app.include_router(inventory_router, prefix="/api")
app.include_router(company_router, prefix="/api")
app.include_router(game_router, prefix="/api")
app.include_router(control_plane_router)
app.include_router(contract_router)
app.include_router(execution_router)
app.include_router(alerts_router)
app.include_router(observability_router)
app.include_router(rollout_readiness_router)
app.include_router(agent_router, prefix="/api")
app.include_router(world_router, prefix="/api")
app.include_router(skills_router, prefix="/api")
app.include_router(transport_router, prefix="/api")
app.include_router(guild_router, prefix="/api")
app.include_router(diplomacy_router, prefix="/api")
app.include_router(strategy_router, prefix="/api")
app.include_router(decisions_router, prefix="/api")
app.include_router(warfare_router, prefix="/api")
app.include_router(autonomy_router, prefix="/api")
app.include_router(digest_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(market_analysis_router, prefix="/api")

if settings.MCP_SURFACE_ENABLED:
    from agentropolis.mcp.server import mcp

    app.mount("/mcp", mcp.streamable_http_app())


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/meta/runtime")
async def runtime_metadata(session: AsyncSession = Depends(get_session)):
    """Machine-readable snapshot of the current scaffold/runtime surface."""
    return build_runtime_metadata(
        preview_guard_state=await get_preview_guard_state(session)
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException):
    """Expose stable error metadata for HTTP-layer failures."""
    headers = dict(exc.headers or {})
    request_id = getattr(request.state, "request_id", None)
    if request_id and REQUEST_ID_HEADER not in headers:
        headers[REQUEST_ID_HEADER] = request_id

    content = {"detail": exc.detail}
    if request_id:
        content["request_id"] = request_id

    error_code = headers.get(ERROR_CODE_HEADER)
    if error_code:
        content["error_code"] = error_code

    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_exception(request: Request, exc: RequestValidationError):
    """Expose request validation failures through the same error contract."""
    request_id = getattr(request.state, "request_id", None)
    headers = {ERROR_CODE_HEADER: "request_validation_failed"}
    if request_id:
        headers[REQUEST_ID_HEADER] = request_id

    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "error_code": "request_validation_failed",
            **({"request_id": request_id} if request_id else {}),
        },
        headers=headers,
    )


@app.exception_handler(NotImplementedError)
async def handle_not_implemented(request: Request, exc: NotImplementedError):
    """Expose scaffold placeholders as HTTP 501 instead of generic 500s."""
    request_id = getattr(request.state, "request_id", None)
    error_code = "not_implemented"
    headers = {ERROR_CODE_HEADER: error_code}
    if request_id:
        headers[REQUEST_ID_HEADER] = request_id
    return JSONResponse(
        status_code=501,
        content={
            "detail": str(exc) or "This scaffold endpoint is not implemented yet.",
            "status": "not_implemented",
            "error_code": error_code,
            **({"request_id": request_id} if request_id else {}),
        },
        headers=headers,
    )
