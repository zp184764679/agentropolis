"""Small helper for stable structured log payloads."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from typing import Any


def emit_structured_log(
    logger: logging.Logger,
    event: str,
    *,
    level: str = "info",
    **fields: Any,
) -> None:
    payload = {
        "event": event,
        "ts": datetime.now(UTC).isoformat(),
        **fields,
    }
    getattr(logger, level.lower())(
        json.dumps(payload, ensure_ascii=True, sort_keys=True)
    )
