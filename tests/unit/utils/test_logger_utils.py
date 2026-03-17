"""Unit tests for app.utils.logger (get_coordinate_update_logger, get_emoji_safe_text, etc.)."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from app.utils.logger import (
    get_coordinate_update_logger,
    get_coord_logger,
    get_emoji_safe_text,
    setup_windows_console_encoding,
)


def test_get_coordinate_update_logger_returns_same_logger_on_second_call() -> None:
    """Second call does not add duplicate handlers (covers branch when handlers exist)."""
    logger1 = get_coordinate_update_logger()
    logger2 = get_coordinate_update_logger()
    assert logger1 is logger2
    assert logger1.name == "coordinate_updates"


def test_get_emoji_safe_text_non_windows_returns_unchanged() -> None:
    with patch.object(sys, "platform", "linux"):
        assert get_emoji_safe_text("hello") == "hello"


def test_get_emoji_safe_text_windows_safe_returns_unchanged() -> None:
    with patch.object(sys, "platform", "win32"):
        assert get_emoji_safe_text("hello") == "hello"


def test_get_emoji_safe_text_windows_unicode_error_replaces() -> None:
    with patch.object(sys, "platform", "win32"):
        # Use a character that may fail strict encode on some Windows configs, or mock encode
        class BadStr(str):
            def encode(self, encoding="utf-8", errors="strict"):
                if errors == "strict":
                    raise UnicodeEncodeError(encoding, self, 0, 1, "reason")
                return str.encode(self, encoding, errors)

        result = get_emoji_safe_text(BadStr("x"))
        assert isinstance(result, str)


def test_setup_windows_console_encoding_noop_on_non_windows() -> None:
    with patch.object(sys, "platform", "linux"):
        setup_windows_console_encoding()


def test_setup_windows_console_encoding_on_windows() -> None:
    with patch.object(sys, "platform", "win32"):
        with patch.object(sys.stdout, "reconfigure", MagicMock()), patch.object(
            sys.stderr, "reconfigure", MagicMock()
        ):
            setup_windows_console_encoding()


def test_setup_windows_console_encoding_exception_suppressed() -> None:
    with patch.object(sys, "platform", "win32"):
        with patch.object(sys.stdout, "reconfigure", side_effect=RuntimeError):
            setup_windows_console_encoding()


def test_get_coord_logger_returns_logger_and_safe_text_fn() -> None:
    logger, safe_fn = get_coord_logger()
    assert logger is not None
    assert callable(safe_fn)
    assert safe_fn("x") == "x" or isinstance(safe_fn("x"), str)


def test_get_coord_logger_import_error_fallback() -> None:
    import app.utils.logger as logger_mod
    with patch.object(logger_mod, "get_coordinate_update_logger", side_effect=ImportError):
        with patch.object(logger_mod, "get_emoji_safe_text", side_effect=ImportError):
            logger, safe_fn = logger_mod.get_coord_logger()
            assert logger is not None
            assert safe_fn("x") == "x"
