"""
Run the data pipeline scripts sequentially in one command.

This orchestrator preserves existing behavior by invoking each script exactly as
you would run it manually. It does not alter script internals.

Usage:
  python scripts/run_full_data_pipeline.py
  python scripts/run_full_data_pipeline.py --csv-path data/abdoun_merged_properties.csv
  python scripts/run_full_data_pipeline.py --skip-optional
  python scripts/run_full_data_pipeline.py --skip-translate-other-languages
  python scripts/run_full_data_pipeline.py --skip-script update_more_features.py --skip-script backfill_feature_values_from_csv.py
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _run_command(command: list[str]) -> int:
    """Run a command and stream output; return its exit code."""
    print("\n" + "=" * 100)
    print("Running:", " ".join(command))
    print("=" * 100)
    proc = subprocess.run(command, check=False)
    return int(proc.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run all data scripts sequentially with fail-fast behavior."
    )
    parser.add_argument(
        "--csv-path",
        type=str,
        default="data/abdoun_merged_properties.csv",
        help="CSV path for scripts that accept CSV input.",
    )
    parser.add_argument(
        "--skip-optional",
        action="store_true",
        help="Skip optional enrichment/backfill steps.",
    )
    parser.add_argument(
        "--skip-translate-other-languages",
        action="store_true",
        help="Skip multilingual translation step (ar/esp/fr).",
    )
    parser.add_argument(
        "--skip-script",
        action="append",
        default=[],
        help=(
            "Script filename to skip (repeatable). "
            "Example: --skip-script update_more_features.py"
        ),
    )
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}")
        return 1

    py = sys.executable
    commands: list[list[str]] = [
        [py, "scripts/seed_rbac.py"],
        [py, "scripts/verify_rbac.py"],
        [py, "scripts/seed_reference_data.py"],
        [py, "scripts/import_normalized_csv.py", "--csv-path", str(csv_path)],
    ]

    if not args.skip_optional:
        # Keep compatibility with existing positional CSV argument.
        commands.extend(
            [
                [py, "scripts/update_more_features.py", str(csv_path)],
                [py, "scripts/backfill_reference_number.py", "--csv-path", str(csv_path)],
                [py, "scripts/update_pricing_extras.py"],
                [py, "scripts/backfill_meta_features_from_csv.py", "--csv-path", str(csv_path)],
                [py, "scripts/backfill_feature_values_from_csv.py", "--csv-path", str(csv_path)],
                [py, "scripts/backfill_property_translations.py"],
            ]
        )
        if not args.skip_translate_other_languages:
            commands.append(
                [py, "scripts/backfill_property_translations.py", "--translate-other-languages"]
            )
        commands.append([py, "scripts/update_exclusive_properties.py"])

    commands.append([py, "scripts/check_data_status.py"])

    skip_set = {name.strip().lower() for name in args.skip_script if name and name.strip()}
    if skip_set:
        filtered_commands: list[list[str]] = []
        for cmd in commands:
            script_name = Path(cmd[1]).name.lower() if len(cmd) > 1 else ""
            if script_name in skip_set:
                print(f"Skipping by --skip-script: {script_name}")
                continue
            filtered_commands.append(cmd)
        commands = filtered_commands

    total = len(commands)
    for idx, cmd in enumerate(commands, start=1):
        print(f"\nStep {idx}/{total}")
        code = _run_command(cmd)
        if code != 0:
            print(f"\nPipeline stopped at step {idx}/{total}. Exit code: {code}")
            return code

    print("\nPipeline completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
