"""Test Suite for NetSage-AI Rule Checker across all 30 cases."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = PROJECT_ROOT / "data" / "cases.csv"

sys.path.insert(0, str(PROJECT_ROOT / "python"))

from rule_checker import evaluate_case_rules


def test_rule_checker() -> None:
    if not CASES_PATH.exists():
        print(f"Error: {CASES_PATH} not found.")
        sys.exit(1)

    with CASES_PATH.open("r", encoding="utf-8") as f:
        cases = list(csv.DictReader(f))

    print(f"=== NetSage-AI Rule Checker Audit ({len(cases)} cases) ===")
    print(f"{'ID':<4} {'Category':<15} {'Case Title':<38} {'Findings':<10} {'Details'}")
    print("-" * 90)

    total_with_findings = 0
    total_insufficient = 0

    for c in cases:
        cid = c["case_id"]
        cat = c.get("category", "")
        title = c.get("case_title", "")
        res = evaluate_case_rules(c)
        findings = res.get("rule_checker_findings", [])

        is_insufficient = "insufficient evidence" in c.get("expected_fault", "").lower() or c.get("osi_layer") == "Unknown"
        if is_insufficient:
            total_insufficient += 1
        elif len(findings) > 0:
            total_with_findings += 1

        details = ""
        if findings:
            details = "; ".join(f"[{f.get('issue')}] {f.get('evidence')}" for f in findings)
        else:
            details = "No findings (Insufficient Evidence / No config rule match)"

        print(f"{cid:<4} {cat:<15} {title[:36]:<38} {len(findings):<10} {details[:45]}")

    print("-" * 90)
    print(f"Summary: {len(cases)} total cases processed.")
    print(f"  - Cases with detected rule findings: {total_with_findings}")
    print(f"  - Cases with insufficient evidence: {total_insufficient}")


if __name__ == "__main__":
    test_rule_checker()
