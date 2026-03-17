from __future__ import annotations

from typing import Any

from app.utils.request_context import get_request_id


def init_sentry(*, dsn: str, environment: str) -> None:
    """Initialize Sentry error tracking.

    Notes:
        - This must never crash application startup.
        - We intentionally avoid adding request bodies/PII. Sentry will capture
          stack traces and request metadata by default; request_id is added as a tag.
    """
    import sentry_sdk
    from sentry_sdk.integrations.starlette import StarletteIntegration

    def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
        rid = get_request_id()
        if rid:
            event.setdefault("tags", {})
            event["tags"]["request_id"] = rid
        return event

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        integrations=[StarletteIntegration()],
        send_default_pii=False,
        before_send=before_send,
    )

