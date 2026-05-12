"""Strict validation for in-app notification payloads."""

from __future__ import annotations

import re
import uuid
from typing import Any, Mapping

from app.constants.notification_messages import NOTIFICATION_MESSAGES
from app.services.notification_route_registry import NotificationRouteRegistry


_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _flatten_template_data(data: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(data)
    meta = data.get("metadata")
    if isinstance(meta, Mapping):
        for k, v in meta.items():
            out[f"metadata.{k}"] = v
            if k not in out:
                out[k] = v
    return out


def _placeholder_keys(template: str) -> frozenset[str]:
    return frozenset(_PLACEHOLDER_RE.findall(template))


class NotificationValidator:
    @staticmethod
    def validate_recipient_user_id(*, recipient_user_id: uuid.UUID) -> None:
        if not isinstance(recipient_user_id, uuid.UUID):
            raise ValueError("recipient_user_id must be a uuid.UUID")

    @staticmethod
    def validate_type_key_has_template(*, type_key: str) -> None:
        if type_key not in NOTIFICATION_MESSAGES:
            raise ValueError(f"Unknown notification type_key (no template): {type_key!r}")

    @staticmethod
    def validate_event_type_registered(*, event_type: str) -> None:
        if not NotificationRouteRegistry.is_known_event(event_type):
            raise ValueError(f"Unknown notification event_type (not in route registry): {event_type!r}")

    @staticmethod
    def validate_placeholders_resolved(*, type_key: str, data: Mapping[str, Any] | None) -> None:
        templates = NOTIFICATION_MESSAGES[type_key]
        title_tpl = str(templates.get("title", ""))
        msg_tpl = str(templates.get("message", ""))
        required = _placeholder_keys(title_tpl) | _placeholder_keys(msg_tpl)
        if not required:
            return
        flat = _flatten_template_data(data or {})
        missing = sorted(k for k in required if k not in flat or flat[k] is None)
        if missing:
            raise ValueError(
                f"Missing or null template placeholder(s) for type_key={type_key!r}: {missing}"
            )

    @classmethod
    def validate_dispatch(
        cls,
        *,
        event_type: str,
        type_key: str,
        recipient_user_id: uuid.UUID,
        data: Mapping[str, Any] | None,
    ) -> None:
        cls.validate_recipient_user_id(recipient_user_id=recipient_user_id)
        cls.validate_type_key_has_template(type_key=type_key)
        cls.validate_event_type_registered(event_type=event_type)
        cls.validate_placeholders_resolved(type_key=type_key, data=data)
