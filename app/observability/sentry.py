"""Initialize Sentry SDK for error tracking; request_id attached as tag when available."""
from __future__ import annotations

from typing import Any

from app.utils.constants import RequestIdConstants
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.logger import api_logger
from app.utils.request_context import get_request_id


def init_sentry(*, dsn: str, environment: str) -> None:
    """Initialize Sentry; must not crash startup. Adds request_id tag; no request bodies/PII.

    Args:
        dsn: Sentry DSN.
        environment: Environment name (e.g. local, production).
    """
    try:
        import sentry_sdk
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError as exc:  # pragma: no cover - optional dependency
        api_logger.warning(
            format_log_message(LogMessages.Observability.SENTRY_INIT_SKIPPED, error=str(exc))
        )
        return

    def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
        rid = get_request_id()
        if rid:
            event.setdefault("tags", {})
            event["tags"][RequestIdConstants.SENTRY_TAG_REQUEST_ID] = rid
        return event

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        integrations=[StarletteIntegration()],
        send_default_pii=False,
        before_send=before_send,
    )

