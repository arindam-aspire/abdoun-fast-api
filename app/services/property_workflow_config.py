from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.json_config import load_json_config


class PropertyWorkflowConfig:
    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw
        self.statuses = raw.get("statuses") or {}
        self.labels = raw.get("labels") or {}
        self.transitions = raw.get("transitions") or {}
        self.rules = raw.get("rules") or {}

    def status(self, key: str) -> str:
        value = self.statuses.get(key)
        if not isinstance(value, str) or not value:
            raise RuntimeError(f"Property workflow status is not configured: {key}")
        return value

    def label(self, status: str) -> str:
        return str(self.labels.get(status) or status)

    def transition(self, key: str) -> str:
        value = self.transitions.get(key)
        if not isinstance(value, str) or not value:
            raise RuntimeError(f"Property workflow transition is not configured: {key}")
        return value

    def enabled(self, key: str, *, default: bool = False) -> bool:
        value = self.rules.get(key)
        return default if value is None else bool(value)


@lru_cache
def get_property_workflow_config() -> PropertyWorkflowConfig:
    return PropertyWorkflowConfig(load_json_config("property_workflow.json"))
