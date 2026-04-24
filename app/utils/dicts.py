"""Dictionary helper utilities."""

from typing import Any


def deep_merge_dict(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries while replacing arrays from `new`.

    - Nested dicts are merged recursively.
    - Lists/arrays are replaced by the incoming value.
    - Scalars are replaced by the incoming value.
    """
    merged: dict[str, Any] = dict(old)
    for key, new_value in new.items():
        old_value = merged.get(key)
        if isinstance(old_value, dict) and isinstance(new_value, dict):
            merged[key] = deep_merge_dict(old_value, new_value)
        else:
            merged[key] = new_value
    return merged
