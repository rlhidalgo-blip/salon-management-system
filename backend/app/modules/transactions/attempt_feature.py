"""Single, process-stable cutover switch for attempt APIs and both sale writers.

Deployment must migrate first, stop legacy workers, then start only workers with
SALE_ATTEMPT_PROTOCOL_ENABLED=1. The default is deliberately disabled.
"""

import os
from functools import lru_cache

from app.core.exceptions import ApiError


@lru_cache(maxsize=1)
def attempt_protocol_enabled() -> bool:
    value = os.getenv("SALE_ATTEMPT_PROTOCOL_ENABLED", "0")
    if value not in ("0", "1"):
        raise RuntimeError("Invalid SALE_ATTEMPT_PROTOCOL_ENABLED value")
    return value == "1"


def require_attempt_protocol() -> None:
    if not attempt_protocol_enabled():
        raise ApiError(404, "not_found", "Request failed", headers={"Cache-Control": "no-store"})
