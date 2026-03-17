from __future__ import annotations

from app.utils.log_messages import format_log_message


def test_format_log_message_formats_when_all_keys_present() -> None:
    assert format_log_message("Hello {name}", name="World") == "Hello World"


def test_format_log_message_returns_template_when_key_missing() -> None:
    assert format_log_message("Hello {name}") == "Hello {name}"

