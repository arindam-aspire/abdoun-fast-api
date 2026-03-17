from __future__ import annotations

import time
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.utils.logger import db_logger
from app.utils.request_context import get_request_id


def install_slow_query_logging(*, engine: Engine, threshold_ms: int) -> None:
    """Log SQL statements that exceed the given duration threshold.

    Notes:
        - We do not log bind parameters to reduce risk of leaking sensitive data.
        - Correlates slow queries to requests via request_id when available.
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
            rid = get_request_id() or "-"
            db_logger.warning(
                "slow_query duration_ms=%.2f threshold_ms=%d request_id=%s statement=%s",
                duration_ms,
                threshold_ms,
                rid,
                _normalize_statement(statement),
            )


def _normalize_statement(statement: Any) -> str:
    try:
        s = str(statement)
    except Exception:
        return "<unprintable>"
    # Keep logs compact.
    s = " ".join(s.split())
    if len(s) > 2000:
        return s[:2000] + "…"
    return s

