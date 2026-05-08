"""Notification template service (Phase 1).

Builds title/message strings from centralized constants and does lightweight
placeholder substitution using the notification payload (data).
"""

from __future__ import annotations

from typing import Any, Mapping

from app.constants.notification_messages import NOTIFICATION_MESSAGES


class NotificationTemplateService:
    def build(self, *, type_key: str, data: Mapping[str, Any] | None = None) -> tuple[str, str]:
        templates = NOTIFICATION_MESSAGES.get(type_key)
        if not templates:
            # Safe fallback for unknown types (should not happen in normal flows).
            return ("Notification", "You have a new notification.")

        title_tpl = templates.get("title", "Notification")
        msg_tpl = templates.get("message", "You have a new notification.")
        if not data:
            return (title_tpl, msg_tpl)

        flat = _flatten_template_data(data)
        return (_safe_format(title_tpl, flat), _safe_format(msg_tpl, flat))


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


def _safe_format(template: str, values: Mapping[str, Any]) -> str:
    # Use str.format_map with a dict that returns "{key}" for missing keys.
    class _Missing(dict):
        def __missing__(self, key: str) -> str:  # type: ignore[override]
            return "{" + key + "}"

    return template.format_map(_Missing(values))

