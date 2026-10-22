"""Comprehensive Dataset & Pipeline Health Validation Script for NetSage-AI.

Validates:
1. data/cases.csv: Required fields, unique IDs, valid severity/category values, and optional pkt_file references.
2. Packet Tracer (.pkt) Files: Checks whether referenced .pkt files exist in packet_tracer_30-cases/.
   Shows PASS if the file exists, or WARNING if not yet added (non-fatal).
3. Cross-referencing: Confirms that every case_id in diagnosis_results.csv,
   human_review.csv, responsible_ai_log.csv, and diagnosis_responses/
   actually exists in data/cases.csv.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = PROJECT_ROOT / "data" / "cases.csv"
RESULTS_DIR = PROJECT_ROOT / "results"
DIAGNOSIS_RESULTS_PATH = RESULTS_DIR / "diagnosis_results.csv"
HUMAN_REVIEW_PATH = RESULTS_DIR / "human_review.csv"
RESPONSIBLE_AI_LOG_PATH = RESULTS_DIR / "responsible_ai_log.csv"
RESPONSES_DIR = RESULTS_DIR / "diagnosis_responses"

REQUIRED_FIELDS = [
    "case_id", "case_title", "symptom", "topology_note", "show_commands",
    "show_output", "expected_fault", "osi_layer", "category", "concept",
    "severity", "expected_fix"
]

VALID_SEVERITIES = {"High", "Medium", "Low"}
VALID_CATEGORIES = {
    "VLAN", "Gateway", "DHCP", "DNS", "Routing", "ACL", "NAT", "Wireless", "IP Addressing", "Interface"
}


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    """Load CSV lines, skipping comment lines starting with #."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        lines = [line for line in handle if not line.strip().startswith("#")]
    reader = csv.DictReader(lines)
    return list(reader)


def validate_dataset(path: Path = CASES_PATH) -> tuple[bool, list[str], list[str], set[str], dict[str, int]]:
    """Validate case data completeness, consistency, pkt_file existence, and cross-file references.
    
    Returns:
        (is_valid, errors, warnings, valid_case_ids, pkt_stats)
    """
    if not path.exists():
        return False, [f"Dataset file not found: {path}"], [], set(), {}

    errors: list[str] = []
    warnings: list[str] = []
    valid_ids: set[str] = set()
    pkt_stats = {"total_cases": 0, "pkt_attached": 0, "pkt_missing": 0}

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return False, ["Dataset file is empty or unreadable."], [], set(), {}

        missing_columns = [col for col in REQUIRED_FIELDS if col not in reader.fieldnames]
        if missing_columns:
            errors.append(f"Missing required columns in cases.csv header: {', '.join(missing_columns)}")

        rows = list(reader)

    if not rows:
        return False, ["Dataset contains zero case rows."], [], set(), {}

    pkt_stats["total_cases"] = len(rows)
    print(f"Loaded {len(rows)} troubleshooting cases for validation (Dataset progress: {len(rows)} / 30 cases).")

    for index, row in enumerate(rows, start=1):
        case_id = row.get("case_id", "").strip()
        label = f"Row {index} (Case ID: {case_id or 'MISSING'})"

        if not case_id:
            errors.append(f"{label}: case_id is missing.")
        elif case_id in valid_ids:
            errors.append(f"{label}: duplicate case_id '{case_id}' found in cases.csv.")
        else:
            valid_ids.add(case_id)

        for field in REQUIRED_FIELDS:
            if field == "case_id":
                continue
            val = (row.get(field) or "").strip()
            if not val:
                errors.append(f"{label}: field '{field}' is empty.")

        sev = (row.get("severity") or "").strip()
        if sev and sev not in VALID_SEVERITIES:
            errors.append(f"{label}: invalid severity '{sev}'. Must be one of {sorted(VALID_SEVERITIES)}.")

        cat = (row.get("category") or "").strip()
        if cat and cat not in VALID_CATEGORIES:
            errors.append(f"{label}: unrecognized category '{cat}'. Expected one of {sorted(VALID_CATEGORIES)}.")

        # Validate optional pkt_file column
        pkt_rel_path = (row.get("pkt_file") or "").strip()
        if pkt_rel_path:
            pkt_full_path = PROJECT_ROOT / pkt_rel_path
            if pkt_full_path.exists():
                pkt_stats["pkt_attached"] += 1
            else:
                pkt_stats["pkt_missing"] += 1
                warnings.append(f"{label}: Packet Tracer file '{pkt_rel_path}' is referenced but not yet added to disk.")
        else:
            pkt_stats["pkt_missing"] += 1
            warnings.append(f"{label}: No Packet Tracer file referenced in pkt_file column.")

    # Cross-referencing Validation against Result/Review files
    check_files = [
        (DIAGNOSIS_RESULTS_PATH, "diagnosis_results.csv"),
        (HUMAN_REVIEW_PATH, "human_review.csv"),
        (RESPONSIBLE_AI_LOG_PATH, "responsible_ai_log.csv"),
    ]

    for fpath, fname in check_files:
        if fpath.exists():
            frows = load_csv_rows(fpath)
            for idx, r in enumerate(frows, start=1):
                cid = r.get("case_id", "").strip()
                if cid and cid not in valid_ids:
                    errors.append(f"{fname} (Row {idx}): references non-existent case_id '{cid}' not present in cases.csv.")

    if RESPONSES_DIR.exists():
        for resp_file in RESPONSES_DIR.glob("case_*.json"):
            stem = resp_file.stem  # e.g., case_01
            try:
                cid_num = str(int(stem.replace("case_", "")))
                if cid_num not in valid_ids:
                    errors.append(f"diagnosis_responses/{resp_file.name}: references non-existent case_id '{cid_num}' not present in cases.csv.")
            except ValueError:
                pass

    is_valid = len(errors) == 0
    return is_valid, errors, warnings, valid_ids, pkt_stats


def main() -> int:
    print("=== NetSage-AI Dataset & Pipeline Health Validation ===")
    is_valid, errors, warnings, valid_ids, pkt_stats = validate_dataset()

    print(f"\nPacket Tracer Lab Files Summary:")
    print(f"  • Total Cases: {pkt_stats.get('total_cases', 0)}")
    print(f"  • Cases with .pkt Files on Disk: {pkt_stats.get('pkt_attached', 0)}")
    print(f"  • Cases without .pkt Files on Disk: {pkt_stats.get('pkt_missing', 0)}")

    if warnings:
        print(f"\n[WARNINGS] {len(warnings)} non-fatal warning(s) for missing Packet Tracer files:")
        for w in warnings:
            print(f"  [NOTICE] {w}")

    if is_valid:
        print(f"\n[SUCCESS] Dataset validation SUCCESSFUL. All {len(valid_ids)} cases contain valid required fields.")
        print("[SUCCESS] All result, review, and response files reference existing case IDs only.")
        return 0
    else:
        print(f"\n[FAILED] Dataset validation FAILED with {len(errors)} error(s):\n")
        for err in errors:
            print(f"  [ERROR] {err}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
