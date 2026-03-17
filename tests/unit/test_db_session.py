"""Unit tests for app.db.session."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.db import session as session_mod


def test_build_engine_kwargs_sqlite() -> None:
    out = session_mod._build_engine_kwargs("sqlite:///file.db")
    assert out == {"future": True}


def test_build_engine_kwargs_postgres() -> None:
    out = session_mod._build_engine_kwargs("postgresql://localhost/db")
    assert "future" in out
    assert "pool_size" in out
    assert "pool_pre_ping" in out


def test_get_db_yields_and_closes() -> None:
    mock_db = MagicMock()
    with patch.object(session_mod, "SessionLocal", return_value=mock_db):
        gen = session_mod.get_db()
        db = next(gen)
        assert db is mock_db
        try:
            gen.send(None)
        except StopIteration:
            pass
    mock_db.close.assert_called_once()
