"""Install SQLAlchemy event listeners to log queries slower than a configurable threshold."""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.utils.constants import RequestIdConstants
from app.utils.logger import db_logger
from app.utils.log_messages import LogMessages
from app.utils.request_context import get_request_id


def install_slow_query_logging(*, engine: Engine, threshold_ms: int) -> None:
    """Install SQLAlchemy listeners to log queries exceeding threshold_ms; no bind params logged.

    Args:
        engine: SQLAlchemy engine to attach listeners to.
        threshold_ms: Minimum duration in ms to log (ignored if <= 0).

    Notes:
        Does not log bind parameters to avoid leaking sensitive data; uses request_id when set.
    """
    if threshold_ms <= 0:
        return

    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(  # type: ignore[no-untyped-def]
        conn, cursor, statement, parameters, context, executemany
    ):
        conn.info.setdefault("_query_start_time", []).append(time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(  # type: ignore[no-untyped-def]
        conn, cursor, statement, parameters, context, executemany
    ):
        start_times: list[float] = conn.info.get("_query_start_time", [])
        if not start_times:
            return
        start = start_times.pop()
        duration_ms = (time.perf_counter() - start) * 1000.0
        if duration_ms >= threshold_ms:
            rid = get_request_id() or RequestIdConstants.EMPTY_PLACEHOLDER
            db_logger.warning(
                LogMessages.SlowQuery.LOG_TEMPLATE,
                duration_ms,
                threshold_ms,
                rid,
                _normalize_statement(statement),
            )


def _normalize_statement(statement: Any) -> str:
    """Make statement safe for logging: single line, truncated; unprintable becomes placeholder.

    Args:
        statement: Raw SQL statement (may be bytes or object).

    Returns:
        Normalized string, or placeholder if str(statement) fails.
    """
    try:
        s = str(statement)
    except Exception:
        return LogMessages.SlowQuery.UNPRINTABLE_STATEMENT
    s = " ".join(s.split())
    if len(s) > 2000:
        return s[:2000] + "…"
    return s

