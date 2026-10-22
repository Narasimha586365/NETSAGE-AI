"""Shared local data flow for the NetSage AI Packet Tracer prototype."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = PROJECT_ROOT / "data" / "cases.csv"
RESULTS_DIR = PROJECT_ROOT / "results"
DIAGNOSIS_RESULTS_PATH = RESULTS_DIR / "diagnosis_results.csv"
HUMAN_REVIEW_PATH = RESULTS_DIR / "human_review.csv"
RESPONSIBLE_AI_LOG_PATH = RESULTS_DIR / "responsible_ai_log.csv"
COMPARISON_CSV_PATH = RESULTS_DIR / "diagnosis_comparison.csv"
OUTPUT_SUMMARY_CSV_PATH = RESULTS_DIR / "dashboard_summary.csv"
RESPONSES_DIR = RESULTS_DIR / "diagnosis_responses"

sys.path.insert(0, str(PROJECT_ROOT / "python"))
from ai_diagnosis import AIDiagnosisProvider
from rule_checker import evaluate_case_rules

DIAGNOSIS_FIELDS = ["case_id", "diagnosis_id", "diagnosis_source", "provider", "model", "root_cause", "osi_layer", "confidence", "evidence", "next_command", "fix_steps", "verification", "rule_checker_findings"]
REVIEW_FIELDS = ["case_id", "diagnosis_source", "diagnosis_id", "ai_diagnosis", "human_status", "final_diagnosis", "review_notes", "reason_for_correction", "reviewer", "review_date"]
CORRECTION_FIELDS = ["case_id", "diagnosis_source", "diagnosis", "human_status", "final_diagnosis", "reason_for_correction", "reviewer", "review_date"]


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(line for line in handle if not line.lstrip().startswith("#")))


def write_csv_rows(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_cases() -> list[dict[str, str]]: return load_csv_rows(CASES_PATH)
def load_human_reviews() -> list[dict[str, str]]: return load_csv_rows(HUMAN_REVIEW_PATH)
def load_diagnosis_results() -> list[dict[str, str]]: return load_csv_rows(DIAGNOSIS_RESULTS_PATH)
def load_responsible_ai_log() -> list[dict[str, str]]: return load_csv_rows(RESPONSIBLE_AI_LOG_PATH)
def load_diagnosis_comparison() -> list[dict[str, str]]: return load_csv_rows(COMPARISON_CSV_PATH)


def packet_tracer_status(case: dict[str, str]) -> dict[str, str | bool]:
    relative_path = (case.get("pkt_file") or "").strip()
    available = bool(relative_path) and (PROJECT_ROOT / relative_path).is_file()
    return {
        "rel_path": relative_path,
        "filename": Path(relative_path).name if relative_path else "",
        "exists": available,
        "status_label": "Available" if available else "Not available",
    }


def compare_diagnosis_to_human(diagnosis: dict[str, str], review: dict[str, str] | None) -> str:
    """Report an outcome only from a saved human decision, never an assumed match."""
    if not review:
        return "PENDING"
    status = review.get("human_status", "")
    if status == "Accepted":
        return "AGREE"
    if status in {"Edited", "Rejected"}:
        return "DISAGREE"
    return "UNCERTAIN"


def calculate_all_metrics() -> dict[str, Any]:
    cases, reviews, diagnoses = load_cases(), load_human_reviews(), load_diagnosis_results()
    review_map = {row.get("case_id"): row for row in reviews}
    diagnosis_map = {row.get("case_id"): row for row in diagnoses}
    category_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {}
    statuses = {"Accepted": 0, "Edited": 0, "Rejected": 0, "Pending": 0}
    outcomes = {"AGREE": 0, "DISAGREE": 0, "UNCERTAIN": 0, "PENDING": 0}
    device_map: dict[str, dict[str, Any]] = {}
    for case in cases:
        category = case.get("category", "Other")
        severity = case.get("severity", "Unknown")
        category_counts[category] = category_counts.get(category, 0) + 1
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        review = review_map.get(case["case_id"])
        status = review.get("human_status") if review else "Pending"
        status = status if status in statuses else "Pending"
        statuses[status] += 1
        outcome = compare_diagnosis_to_human(diagnosis_map.get(case["case_id"], {}), review)
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        for name in _extract_devices(case):
            entry = device_map.setdefault(name, {"device_name": name, "device_type": _device_type(name), "cases": [], "packet_tracer_files": []})
            entry["cases"].append(case["case_id"])
            status_pkt = packet_tracer_status(case)
            if status_pkt["exists"] and status_pkt["filename"] not in entry["packet_tracer_files"]:
                entry["packet_tracer_files"].append(status_pkt["filename"])
    reviewed = statuses["Accepted"] + statuses["Edited"] + statuses["Rejected"]
    agreement = f"{round((statuses['Accepted'] / reviewed) * 100, 1)}%" if reviewed else "N/A"
    correction = f"{round(((statuses['Edited'] + statuses['Rejected']) / reviewed) * 100, 1)}%" if reviewed else "N/A"
    return {
        "total_cases": len(cases), "reviewed_cases": reviewed, "pending_cases": statuses["Pending"],
        "accepted": statuses["Accepted"], "edited": statuses["Edited"], "rejected": statuses["Rejected"],
        "agreement_rate": agreement, "correction_rate": correction, "category_counts": category_counts,
        "severity_counts": severity_counts, "outcomes": outcomes, "devices": sorted(device_map.values(), key=lambda item: item["device_name"]),
        "responsible_ai_corrections": len(load_responsible_ai_log()),
    }


def _extract_devices(case: dict[str, str]) -> list[str]:
    import re
    values = f"{case.get('topology_note', '')} {case.get('show_output', '')}"
    return sorted(set(re.findall(r"\b(?:PC\d+|SW\d+|R\d+|Server\d+|AP\d+)\b", values)))


def _device_type(name: str) -> str:
    return "Router" if name.startswith("R") else "Switch" if name.startswith("SW") else "Server" if name.startswith("Server") else "Access Point" if name.startswith("AP") else "PC"


def update_summary_csv() -> None:
    metrics = calculate_all_metrics()
    rows = [["Total Cases", metrics["total_cases"]], ["Reviewed", metrics["reviewed_cases"]], ["Pending", metrics["pending_cases"]], ["Accepted", metrics["accepted"]], ["Edited", metrics["edited"]], ["Rejected", metrics["rejected"]], ["Diagnosis vs Human Outcome Rate", metrics["agreement_rate"]], ["Human Correction Rate", metrics["correction_rate"]]]
    try:
        with OUTPUT_SUMMARY_CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle); writer.writerow(["Metric", "Value"]); writer.writerows(rows)
    except PermissionError:
        print("Notice: dashboard_summary.csv is open elsewhere; its refresh was skipped.")


def run_single_case_check(case_id: str) -> dict[str, Any]:
    case = next((item for item in load_cases() if item["case_id"] == str(case_id)), None)
    if not case:
        return {"error": "Case not found.", "status": "EXECUTION_ERROR"}
    try:
        findings = evaluate_case_rules(case).get("rule_checker_findings", [])
        insufficient = "insufficient evidence" in case.get("expected_fault", "").lower() or "unconfirmed" in case.get("case_title", "").lower() or case.get("osi_layer") == "Unknown"
        if findings:
            state = "FINDINGS_DETECTED"
        elif insufficient:
            state = "INSUFFICIENT_EVIDENCE"
        else:
            state = "NO_FINDINGS"
        return {"case_id": str(case_id), "status": state, "source": "DETERMINISTIC_RULE", "rule_checker_findings": findings}
    except Exception as exc:
        return {"case_id": str(case_id), "status": "EXECUTION_ERROR", "source": "DETERMINISTIC_RULE", "error_message": str(exc), "rule_checker_findings": []}


def run_single_case_ai(case_id: str, force: bool = False) -> dict[str, Any]:
    case = next((item for item in load_cases() if item["case_id"] == str(case_id)), None)
    if not case: return {"error": "Case not found."}
    findings = evaluate_case_rules(case).get("rule_checker_findings", [])

    file_path = RESPONSES_DIR / f"case_{int(case_id):02d}.json"
    if not force and file_path.exists():
        try:
            cached_diagnosis = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(cached_diagnosis, dict) and cached_diagnosis.get("diagnosis_source") == "AI_API":
                stored = {row.get("case_id"): row for row in load_diagnosis_results()}
                stored[str(case_id)] = {key: json.dumps(value) if isinstance(value, list) else str(value) for key, value in cached_diagnosis.items()}
                write_csv_rows(DIAGNOSIS_RESULTS_PATH, DIAGNOSIS_FIELDS, [stored[k] for k in sorted(stored, key=int)])
                return {"case_id": str(case_id), "ai_status": "GENERATED", "ai_diagnosis": cached_diagnosis, "rule_checker_findings": findings, "cached": True}
        except Exception:
            pass

    provider = AIDiagnosisProvider()

    def on_retry_log(cid: str, attempt: int, delay: float, err_text: str) -> None:
        print(f"Case {cid}: Gemini rate limit reached. Waiting {int(delay)} seconds before retry...")

    diagnosis, error_message = provider.generate_diagnosis(case, findings, on_retry=on_retry_log)
    if diagnosis is None:
        info = provider.get_provider_info()
        return {"case_id": str(case_id), "ai_status": info["status"], "message": error_message or info["message"], "provider": info, "rule_checker_findings": findings}

    diagnosis_id = f"api_case_{int(case_id):02d}"
    diagnosis.update({"case_id": str(case_id), "diagnosis_id": diagnosis_id, "rule_checker_findings": findings})
    RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(diagnosis, indent=2), encoding="utf-8")

    stored = {row.get("case_id"): row for row in load_diagnosis_results()}
    stored[str(case_id)] = {key: json.dumps(value) if isinstance(value, list) else str(value) for key, value in diagnosis.items()}
    write_csv_rows(DIAGNOSIS_RESULTS_PATH, DIAGNOSIS_FIELDS, [stored[key] for key in sorted(stored, key=int)])
    update_comparison_csv(); update_summary_csv()
    return {"case_id": str(case_id), "ai_status": "GENERATED", "ai_diagnosis": diagnosis, "rule_checker_findings": findings, "cached": False}


def save_human_review(data: dict[str, str]) -> dict[str, Any]:
    """Persist only a reviewer-supplied decision; no defaults or dates are fabricated."""
    case_id = str(data.get("case_id", "")).strip()
    status = str(data.get("human_status", "")).strip()
    reviewer = str(data.get("reviewer", "")).strip()
    final = str(data.get("final_diagnosis", "")).strip()
    if not case_id or status not in {"Accepted", "Edited", "Rejected"}: return {"error": "Choose Accepted, Edited, or Rejected before saving."}
    if not reviewer: return {"error": "Reviewer name is required."}
    if not final: return {"error": "Final diagnosis is required."}
    if status in {"Edited", "Rejected"} and not str(data.get("reason_for_correction", "")).strip(): return {"error": "Reason for correction is required for Edited or Rejected."}
    diagnosis = next((row for row in load_diagnosis_results() if row.get("case_id") == case_id), {})
    record = {"case_id": case_id, "diagnosis_source": diagnosis.get("diagnosis_source", "HUMAN_REVIEW"), "diagnosis_id": diagnosis.get("diagnosis_id", ""), "ai_diagnosis": diagnosis.get("root_cause", ""), "human_status": status, "final_diagnosis": final, "review_notes": str(data.get("review_notes", "")).strip(), "reason_for_correction": str(data.get("reason_for_correction", "")).strip(), "reviewer": reviewer, "review_date": str(data.get("review_date", "")).strip()}
    records = {row.get("case_id"): row for row in load_human_reviews()}; records[case_id] = record
    write_csv_rows(HUMAN_REVIEW_PATH, REVIEW_FIELDS, [records[key] for key in sorted(records, key=int)])
    corrections = {row.get("case_id"): row for row in load_responsible_ai_log()}
    if status in {"Edited", "Rejected"}:
        corrections[case_id] = {
            "case_id": case_id,
            "diagnosis_source": record["diagnosis_source"],
            "diagnosis": record["ai_diagnosis"],
            "human_status": status,
            "final_diagnosis": final,
            "reason_for_correction": record["reason_for_correction"],
            "reviewer": reviewer,
            "review_date": record["review_date"],
        }
    else: corrections.pop(case_id, None)
    write_csv_rows(RESPONSIBLE_AI_LOG_PATH, CORRECTION_FIELDS, [corrections[key] for key in sorted(corrections, key=int)])
    update_comparison_csv(); update_summary_csv()
    return {"status": "SUCCESS", "metrics": calculate_all_metrics()}


def update_comparison_csv() -> None:
    diagnoses = {row.get("case_id"): row for row in load_diagnosis_results()}; reviews = {row.get("case_id"): row for row in load_human_reviews()}
    rows = []
    for case in load_cases():
        diagnosis, review = diagnoses.get(case["case_id"], {}), reviews.get(case["case_id"])
        rows.append({"case_id": case["case_id"], "concept": case.get("concept", ""), "diagnosis_source": diagnosis.get("diagnosis_source", "UNAVAILABLE"), "diagnosis": diagnosis.get("root_cause", ""), "human_status": review.get("human_status", "Pending") if review else "Pending", "final_diagnosis": review.get("final_diagnosis", "") if review else "", "outcome": compare_diagnosis_to_human(diagnosis, review), "reviewer": review.get("reviewer", "") if review else ""})
    write_csv_rows(COMPARISON_CSV_PATH, ["case_id", "concept", "diagnosis_source", "diagnosis", "human_status", "final_diagnosis", "outcome", "reviewer"], rows)
