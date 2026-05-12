"""Notification template service (Phase 1).

Builds title/message strings from centralized constants and does lightweight
placeholder substitution using the notification payload (data).
"""

from __future__ import annotations

from typing import Any, Mapping

from app.constants.notification_messages import NOTIFICATION_MESSAGES


class NotificationTemplateService:
    def build(self, *, type_key: str, data: Mapping[str, Any] | None = None) -> tuple[str, str]:
        """Format title/message. Callers must run NotificationValidator first."""
        templates = NOTIFICATION_MESSAGES.get(type_key)
        if not templates:
            raise KeyError(f"No notification template for type_key={type_key!r}")

        title_tpl = templates.get("title", "Notification")
        msg_tpl = templates.get("message", "You have a new notification.")
        if not data:
            return (str(title_tpl), str(msg_tpl))

        flat = _flatten_template_data(data)
        return (str(title_tpl).format_map(flat), str(msg_tpl).format_map(flat))


def _flatten_template_data(data: Mapping[str, Any]) -> dict[str, Any]:
    # Phase 1: keep it simple; only flatten metadata.* one level.
    out: dict[str, Any] = dict(data)
    meta = data.get("metadata")
    if isinstance(meta, Mapping):
        for k, v in meta.items():
            out[f"metadata.{k}"] = v
            if k not in out:
                out[k] = v
    return out



