import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.metrics import db_pool_checked_out, db_pool_overflow, db_pool_size

logger = structlog.get_logger(__name__)

_SKIP_PATHS = {"/health", "/metrics"}


def _update_pool_metrics() -> None:
    # QueuePool exposes size/checkedout/overflow; NullPool and other pool types do not.
    try:
        from app.db.database import engine
        pool = engine.pool
        if hasattr(pool, "size"):
            db_pool_size.set(pool.size())  # type: ignore[union-attr]
            db_pool_checked_out.set(pool.checkedout())  # type: ignore[union-attr,attr-defined]
            db_pool_overflow.set(pool.overflow())  # type: ignore[union-attr,attr-defined]
    except Exception:
        pass


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        request_id = str(uuid.uuid4())[:8]

        # Bind request_id to all log calls within this request context
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        _update_pool_metrics()

        t0 = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            raise
        finally:
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            log = logger.info if status_code < 400 else logger.warning
            log(
                "request",
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=duration_ms,
            )
