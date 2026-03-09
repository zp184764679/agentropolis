"""Entry point for `python -m agentropolis`."""

import uvicorn

from agentropolis.config import settings

uvicorn.run(
    "agentropolis.main:app",
    host=settings.HOST,
    port=settings.PORT,
    reload=settings.DEBUG,
    log_level=settings.LOG_LEVEL.lower(),
)
