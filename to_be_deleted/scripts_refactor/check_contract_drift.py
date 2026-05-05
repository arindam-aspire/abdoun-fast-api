"""Compare current OpenAPI against legacy baseline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app


def main() -> int:
    baseline_path = ROOT / "docs" / "refactor" / "openapi_legacy_baseline.json"
    if not baseline_path.exists():
        print("baseline_missing")
        return 1

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    current = app.openapi()
    if baseline == current:
        print("no_contract_drift")
        return 0

    baseline_paths = set((baseline.get("paths") or {}).keys())
    current_paths = set((current.get("paths") or {}).keys())
    removed = sorted(baseline_paths - current_paths)
    added = sorted(current_paths - baseline_paths)
    print("contract_drift_detected")
    print(f"removed_paths={len(removed)}")
    print(f"added_paths={len(added)}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

