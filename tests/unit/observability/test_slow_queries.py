"""Unit tests for app.observability.slow_queries."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, text

from app.observability.slow_queries import _normalize_statement, install_slow_query_logging


def test_install_slow_query_logging_skips_when_threshold_zero() -> None:
    engine = create_engine("sqlite:///:memory:")
    install_slow_query_logging(engine=engine, threshold_ms=0)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    # No crash; listeners not added when threshold <= 0


def test_install_slow_query_logging_logs_slow_query() -> None:
    engine = create_engine("sqlite:///:memory:")
    install_slow_query_logging(engine=engine, threshold_ms=1)
    from app.observability import slow_queries as mod

    with patch.object(mod, "db_logger") as mock_log:
        with patch.object(time, "perf_counter", side_effect=[0.0, 1.0]):
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        mock_log.warning.assert_called()
        call_args = str(mock_log.warning.call_args)
        assert "slow_query" in call_args or "duration_ms" in call_args


def test_normalize_statement_returns_unprintable_on_error() -> None:
    class BadStatement:
        def __str__(self) -> str:
            raise RuntimeError("nope")

    assert _normalize_statement(BadStatement()) == "<unprintable>"


def test_normalize_statement_truncates_long() -> None:
    long_s = "SELECT " + "x" * 3000
    out = _normalize_statement(long_s)
    assert len(out) == 2001
    assert out.endswith("…")


def test_install_slow_query_logging_after_cursor_handles_empty_start_times() -> None:
    """Covers after_cursor_execute when _query_start_time is empty (defensive branch)."""
    from sqlalchemy import event

    engine = create_engine("sqlite:///:memory:")
    install_slow_query_logging(engine=engine, threshold_ms=10)

    @event.listens_for(engine, "before_cursor_execute", insert=True)
    def _clear_start_times(conn, cursor, statement, parameters, context, executemany):
        conn.info["_query_start_time"] = []

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    # No crash; after_cursor_execute returns early when start_times is empty
