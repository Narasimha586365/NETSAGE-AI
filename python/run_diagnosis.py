"""Run deterministic checks and optional configured AI API diagnoses."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "python"))

from ai_diagnosis import AIDiagnosisProvider
from data_manager import load_cases, run_single_case_ai, run_single_case_check, update_comparison_csv, update_summary_csv
from validate_dataset import validate_dataset


def run_pipeline(dry_run: bool = False, selected_case_id: int | None = None, force: bool = False) -> int:
    print("=== NetSage AI Diagnosis Pipeline ===")
    valid, errors, warnings, _, _ = validate_dataset()
    if not valid:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    for warning in warnings:
        print(f"NOTICE: {warning}")

    cases = load_cases()
    selected = [case for case in cases if case["case_id"] == str(selected_case_id)] if selected_case_id else cases
    if not selected:
        print("ERROR: requested case does not exist.")
        return 1

    provider = AIDiagnosisProvider().get_provider_info()
    print(f"AI status: {provider['status']} — {provider['message']}")

    if dry_run:
        for case in selected:
            run_single_case_check(case["case_id"])
        print(f"Dry run passed for {len(selected)} case(s). No API call and no result files were written.")
        return 0

    new_calls = 0
    cached_calls = 0

    for idx, case in enumerate(selected):
        cid = case["case_id"]
        check = run_single_case_check(cid)
        print(f"Case {cid}: deterministic status {check['status']}")

        result = run_single_case_ai(cid, force=force)
        if result.get("ai_status") == "GENERATED":
            if result.get("cached"):
                cached_calls += 1
                print(f"Case {cid}: AI API diagnosis already saved.")
            else:
                new_calls += 1
                print(f"Case {cid}: AI API diagnosis saved.")
                if idx < len(selected) - 1:
                    time.sleep(2.5)
        else:
            print(f"Case {cid}: {result.get('message', 'AI diagnosis unavailable.')}")

    update_comparison_csv()
    update_summary_csv()

    total_usable = new_calls + cached_calls
    print(
        f"Completed {len(selected)} case(s). Actual AI API diagnoses: {total_usable} "
        f"(Newly generated: {new_calls}, Reused cached: {cached_calls})."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run NetSage AI local analysis pipeline.")
    parser.add_argument("--dry-run", action="store_true", help="Validate data and deterministic checks only.")
    parser.add_argument("--case", type=int, help="Run one case only.")
    parser.add_argument("--force", action="store_true", help="Force re-generation of AI diagnoses even if saved.")
    args = parser.parse_args()
    return run_pipeline(args.dry_run, args.case, args.force)


if __name__ == "__main__":
    raise SystemExit(main())
