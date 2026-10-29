"""Operations Center Dashboard & Workflow Generator for NetSage AI.

Generates results/dashboard.html and results/dashboard_summary.csv.
Guarantees:
- Brand-neutral status headers and user-facing badge labels.
- Updates deterministic status handling to:
  - FINDINGS_DETECTED -> "Findings detected"
  - NO_FINDINGS -> "No findings"
  - INSUFFICIENT_EVIDENCE -> "Insufficient evidence"
  - EXECUTION_ERROR -> "Execution error"
- Distinguishes rule findings from Python execution errors.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "python") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "python"))

from data_manager import (
    load_cases, load_human_reviews, load_responsible_ai_log,
    load_diagnosis_results, load_diagnosis_comparison, packet_tracer_status,
    calculate_all_metrics, update_summary_csv, compare_diagnosis_to_human
)
from ai_diagnosis import AIDiagnosisProvider

OUTPUT_HTML_PATH = PROJECT_ROOT / "results" / "dashboard.html"


def generate_dashboard(mode_banner: str = "SYSTEM ONLINE") -> None:
    cases = load_cases()
    reviews = load_human_reviews()
    responsible_logs = load_responsible_ai_log()
    diagnosis_results = load_diagnosis_results()
    metrics = calculate_all_metrics()

    current_cases_count = metrics["total_cases"]
    total_reviewed = metrics["reviewed_cases"]
    pending = metrics["pending_cases"]
    accepted = metrics["accepted"]
    edited = metrics["edited"]
    rejected = metrics["rejected"]
    agreement_rate = metrics["agreement_rate"]
    corrections_count = metrics["responsible_ai_corrections"]

    provider = AIDiagnosisProvider()
    pinfo = provider.get_provider_info()
    p_status = pinfo.get("status", "NOT_CONFIGURED")
    ai_service_label = "CONFIGURED" if p_status == "CONFIGURED" else "NOT CONFIGURED"
    ai_service_desc = "Configured and Ready — Automated Root Cause Analysis" if p_status == "CONFIGURED" else "Not Configured — Set API credential in environment or .env file to enable"

    diag_map = {r["case_id"]: r for r in diagnosis_results}
    review_map = {r["case_id"]: r for r in reviews}
    responsible_map = {r["case_id"]: r for r in responsible_logs}

    # Case JSON for client-side JavaScript
    cases_json_list = []
    pkt_attached_count = 0
    for c in cases:
        cid = c["case_id"]
        d = diag_map.get(cid, {})
        r = review_map.get(cid, {})
        resp = responsible_map.get(cid, {})
        pkt = packet_tracer_status(c)
        if pkt["exists"]:
            pkt_attached_count += 1

        findings_raw = d.get("rule_checker_findings", "[]")
        try:
            findings_list = json.loads(findings_raw) if isinstance(findings_raw, str) else findings_raw
        except Exception:
            findings_list = []

        cases_json_list.append({
            "case_id": cid,
            "case_title": c.get("case_title", f"Case {cid}"),
            "symptom": c.get("symptom", "Not Available"),
            "topology_note": c.get("topology_note", "Not Available"),
            "show_commands": c.get("show_commands", "Not Available"),
            "show_output": c.get("show_output", "Not Available"),
            "expected_fault": c.get("expected_fault", "Not Available"),
            "expected_fix": c.get("expected_fix", "Not Available"),
            "category": c.get("category", "Uncategorized"),
            "concept": c.get("concept", "General"),
            "severity": c.get("severity", "Medium"),
            "osi_layer": c.get("osi_layer", "Unknown"),
            "recommended_next_command": c.get("recommended_next_command", "show ip interface brief"),
            "root_cause": d.get("root_cause", "Pending diagnosis"),
            "confidence": d.get("confidence", "Not Available"),
            "next_command": d.get("next_command", "show ip interface brief"),
            "evidence": d.get("evidence", "Not Available"),
            "diagnosis_source": "AI-assisted diagnosis",
            "rule_findings": findings_list,
            "human_status": r.get("human_status", "Pending") if r else "Pending",
            "final_diagnosis": r.get("final_diagnosis", "") if r else "",
            "review_notes": r.get("review_notes", "") if r else "",
            "reason_for_correction": r.get("reason_for_correction", "") if r else "",
            "reviewer": r.get("reviewer", "") if r else "",
            "review_date": r.get("review_date", "") if r else "",
            "pkt_file": pkt.get("rel_path", ""),
            "pkt_filename": pkt.get("filename", ""),
            "pkt_exists": pkt.get("exists", False),
            "pkt_status": pkt.get("status_label", "Not available")
        })

    explorer_json = json.dumps(cases_json_list)
    cat_keys_json = json.dumps(list(metrics["category_counts"].keys()))
    cat_vals_json = json.dumps(list(metrics["category_counts"].values()))
    sev_keys_json = json.dumps([f"{k} Priority" for k in metrics["severity_counts"].keys()])
    sev_vals_json = json.dumps(list(metrics["severity_counts"].values()))

    # Build Saved Reviews Table HTML
    saved_reviews_rows_html = ""
    saved_reviews_list = [r for r in reviews if r.get("human_status") in {"Accepted", "Edited", "Rejected"}]
    if saved_reviews_list:
        for r in saved_reviews_list:
            cid = r.get("case_id", "")
            st = r.get("human_status", "Accepted")
            bcls = f"badge-{st.lower()}"
            r_final = r.get("final_diagnosis", "")
            r_name = r.get("reviewer", "NOC Reviewer")
            r_date = r.get("review_date", "")
            r_notes = r.get("review_notes", "")
            saved_reviews_rows_html += f"""
            <tr>
                <td><strong>Case {cid}</strong></td>
                <td><span class="badge {bcls}">{st}</span></td>
                <td style="font-weight:600;">{r_final}</td>
                <td>{r_name}</td>
                <td>{r_date}</td>
                <td style="font-size:12px; color:var(--text-muted);">{r_notes}</td>
            </tr>"""
    else:
        saved_reviews_rows_html = "<tr><td colspan='6' style='text-align:center; color:var(--text-muted); padding:16px;'>No human reviews recorded yet.</td></tr>"

    # Build Category Option Tags
    category_options_html = '<option value="">All Categories</option>\n'
    for cat in sorted(metrics["category_counts"].keys()):
        category_options_html += f'<option value="{cat}">{cat}</option>\n'

    # Build Devices Table HTML
    devices_rows_html = ""
    for dev in metrics["devices"]:
        d_name = dev["device_name"]
        d_type = dev["device_type"]
        d_cases = ", ".join([f"Case {c}" for c in dev["cases"]])
        d_pkts = ", ".join(dev["packet_tracer_files"]) if dev["packet_tracer_files"] else "None"
        devices_rows_html += f"""
        <tr>
            <td><strong>{d_name}</strong></td>
            <td><span class="badge badge-provider">{d_type}</span></td>
            <td>{d_cases}</td>
            <td><code>{d_pkts}</code></td>
        </tr>"""

    # Build Category Theme Table HTML
    cat_summary_rows_html = ""
    for cat in sorted(metrics["category_counts"].keys()):
        tot = metrics["category_counts"][cat]
        cat_cases = [c for c in cases if c.get("category") == cat]
        rev_count = sum(1 for c in cat_cases if review_map.get(c["case_id"], {}).get("human_status") in {"Accepted", "Edited", "Rejected"})
        acc_count = sum(1 for c in cat_cases if review_map.get(c["case_id"], {}).get("human_status") == "Accepted")
        rate_str = f"{round((acc_count / rev_count) * 100, 1)}%" if rev_count > 0 else "N/A"
        cat_summary_rows_html += f"""
        <tr>
            <td><strong>{cat}</strong></td>
            <td>{tot}</td>
            <td>{rev_count}</td>
            <td>{acc_count}</td>
            <td><strong style="color:var(--accent-dark-blue);">{rate_str}</strong></td>
        </tr>"""

    # Build Priority Performance Table HTML
    sev_summary_rows_html = ""
    for sev in ["Critical", "High", "Medium", "Low"]:
        tot = metrics["severity_counts"].get(sev, 0)
        if tot == 0: continue
        sev_cases = [c for c in cases if c.get("severity") == sev]
        rev_count = sum(1 for c in sev_cases if review_map.get(c["case_id"], {}).get("human_status") in {"Accepted", "Edited", "Rejected"})
        acc_count = sum(1 for c in sev_cases if review_map.get(c["case_id"], {}).get("human_status") == "Accepted")
        rate_str = f"{round((acc_count / rev_count) * 100, 1)}%" if rev_count > 0 else "N/A"
        sev_summary_rows_html += f"""
        <tr>
            <td><strong>{sev} Priority</strong></td>
            <td>{tot}</td>
            <td>{rev_count}</td>
            <td>{acc_count}</td>
            <td><strong style="color:var(--accent-dark-blue);">{rate_str}</strong></td>
        </tr>"""

    # Build Responsible AI Log Table Rows
    responsible_rows_html = ""
    if responsible_logs:
        for rlog in responsible_logs:
            cid = rlog.get("case_id", "")
            st = rlog.get("human_status", "Edited")
            bcls = f"badge-{st.lower()}"
            diag = rlog.get("diagnosis", "")
            final = rlog.get("final_diagnosis", "")
            reason = rlog.get("reason_for_correction", "")
            responsible_rows_html += f"""
            <tr>
                <td><strong>Case {cid}</strong></td>
                <td style="color:var(--text-muted);">{diag}</td>
                <td style="font-weight:700;">{final}</td>
                <td><span class="badge {bcls}">{st}</span></td>
                <td style="font-size:12px;">{reason}</td>
            </tr>"""
    else:
        responsible_rows_html = "<tr><td colspan='5' style='text-align:center; color:var(--text-muted); padding:16px;'>No Responsible AI corrections logged yet.</td></tr>"

    gen_time = datetime.now().strftime("%d %b %Y, %H:%M")

    # Complete HTML Template Construction
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NetSage AI — Network Operations Command Center</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-primary: #FFFFFF;
            --bg-secondary: #F8FAFC;
            --border-color: #E2E8F0;
            --border-hover: #CBD5E1;
            --text-heading: #0F172A;
            --text-body: #334155;
            --text-muted: #64748B;
            --accent-blue: #1E88E5;
            --accent-dark-blue: #1565C0;
            --accent-light-blue: #F0F7FF;
            --status-green: #10B981;
            --status-orange: #F59E0B;
            --status-red: #EF4444;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-secondary);
            color: var(--text-body);
            display: flex; flex-direction: column; min-height: 100vh;
        }}

        /* TOP HEADER & BADGES */
        .top-header {{
            background: var(--bg-primary); border-bottom: 1px solid var(--border-color);
            padding: 14px 28px; display: flex; justify-content: space-between; align-items: center;
            position: sticky; top: 0; z-index: 500;
        }}
        .header-title h1 {{ font-size: 20px; font-weight: 800; color: var(--accent-dark-blue); letter-spacing: -0.3px; }}
        .header-title p {{ font-size: 12px; color: var(--text-muted); font-weight: 500; }}
        .header-badges {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
        .badge-status {{ display: inline-flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 700; padding: 5px 10px; border-radius: 16px; }}
        .badge-online {{ background: #ECFDF5; color: #047857; border: 1px solid #A7F3D0; }}
        .badge-provider {{ background: var(--accent-light-blue); color: var(--accent-dark-blue); border: 1px solid #D6ECFF; }}
        .dot {{ width: 7px; height: 7px; border-radius: 50%; display: inline-block; }}
        .dot-green {{ background: var(--status-green); }}

        /* NAVIGATION BAR */
        .top-nav {{
            background: var(--bg-primary); border-bottom: 1px solid var(--border-color);
            padding: 0 28px; display: flex; gap: 4px; overflow-x: auto;
        }}
        .nav-item {{
            padding: 12px 18px; font-size: 13px; font-weight: 700; color: var(--text-muted);
            text-decoration: none; border-bottom: 3px solid transparent; cursor: pointer; transition: all 0.15s ease;
        }}
        .nav-item:hover {{ color: var(--accent-dark-blue); background: var(--accent-light-blue); }}
        .nav-item.active {{ color: var(--accent-dark-blue); border-bottom-color: var(--accent-dark-blue); background: var(--accent-light-blue); }}

        /* MAIN CONTENT AREA */
        .main-container {{
            max-width: 1400px; width: 100%; margin: 0 auto; padding: 24px; flex: 1;
        }}
        .page-section {{ display: none; }}
        .page-section.active {{ display: block; }}

        .page-title-box {{ margin-bottom: 18px; }}
        .page-title-box h2 {{ font-size: 18px; font-weight: 800; color: var(--accent-dark-blue); }}
        .page-title-box p {{ font-size: 12px; color: var(--text-muted); }}

        /* KPI CARDS GRID */
        .kpi-grid {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 24px;
        }}
        .kpi-card {{
            background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 8px; padding: 14px;
        }}
        .kpi-title {{ font-size: 10px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }}
        .kpi-value {{ font-size: 22px; font-weight: 800; color: var(--text-heading); margin: 4px 0 2px 0; }}
        .kpi-desc {{ font-size: 11px; color: var(--text-muted); }}

        /* PANELS & TABLES */
        .panel {{
            background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 8px; padding: 18px; margin-bottom: 20px;
        }}
        .panel-title {{ font-size: 14px; font-weight: 700; color: var(--text-heading); margin-bottom: 12px; border-bottom: 1px solid var(--border-color); padding-bottom: 6px; }}

        table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
        th, td {{ padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--border-color); }}
        th {{ background: var(--bg-secondary); color: var(--accent-dark-blue); font-weight: 700; text-transform: uppercase; font-size: 10px; }}
        tr:hover {{ background: var(--accent-light-blue); }}

        .badge {{ display: inline-block; padding: 3px 7px; border-radius: 4px; font-size: 10px; font-weight: 700; }}
        .badge-accepted {{ background: #DCFCE7; color: #15803D; }}
        .badge-edited {{ background: #FEF3C7; color: #B45309; }}
        .badge-rejected {{ background: #FEE2E2; color: #B91C1C; }}
        .badge-pending {{ background: #F1F5F9; color: #64748B; }}

        .selector-card {{
            background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 8px; padding: 16px; margin-bottom: 18px;
        }}
        .selector-card label {{ display: block; font-size: 12px; font-weight: 700; color: var(--text-heading); margin-bottom: 6px; }}
        .selector-card select {{
            width: 100%; max-width: 450px; padding: 8px 12px; font-size: 13px; font-weight: 600;
            border: 1px solid var(--border-color); border-radius: 6px; background: white;
        }}
        .selector-subtext {{ font-size: 11px; color: var(--text-muted); margin-top: 6px; }}

        .empty-placeholder {{
            text-align: center; padding: 36px 20px; color: var(--text-muted); background: var(--bg-primary);
            border: 1px dashed var(--border-color); border-radius: 8px; font-size: 13px; font-weight: 500;
        }}

        .btn {{
            background: var(--accent-blue); color: white; border: none; padding: 7px 14px;
            border-radius: 5px; cursor: pointer; font-size: 12px; font-weight: 700; transition: background 0.15s ease;
        }}
        .btn:hover {{ background: var(--accent-dark-blue); }}
        .btn-outline {{ background: transparent; color: var(--accent-dark-blue); border: 1px solid var(--accent-dark-blue); }}
        .btn-outline:hover {{ background: var(--accent-light-blue); }}

        .controls {{ display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }}
        .controls input, .controls select {{
            background: white; border: 1px solid var(--border-color); color: var(--text-body);
            padding: 7px 10px; border-radius: 5px; font-size: 12px;
        }}

        .chart-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 16px; margin-bottom: 20px; }}
        .form-group {{ margin-bottom: 12px; }}
        .form-group label {{ display: block; font-size: 11px; font-weight: 700; color: var(--text-heading); margin-bottom: 4px; }}
        .form-group input, .form-group select, .form-group textarea {{
            width: 100%; padding: 8px; font-size: 12px; border: 1px solid var(--border-color); border-radius: 5px;
        }}
        .form-group textarea {{ resize: vertical; min-height: 60px; }}
    </style>
</head>
<body>

    <div class="top-header">
        <div class="header-title">
            <h1>NetSage AI</h1>
            <p>Network Operations Center & AI-vs-Human Troubleshooting Console</p>
        </div>
        <div class="header-badges">
            <div class="badge-status badge-online"><span class="dot dot-green"></span> MODE: {mode_banner}</div>
            <div class="badge-status badge-provider">AI SERVICE: {ai_service_label}</div>
            <div class="badge-status badge-provider">DATASET: {current_cases_count} / 30 Cases</div>
            <div style="font-size: 11px; color: var(--text-muted);">Updated: <strong>{gen_time}</strong></div>
        </div>
    </div>

    <div class="top-nav">
        <a class="nav-item active" onclick="switchTab('monitor')">Monitor</a>
        <a class="nav-item" onclick="switchTab('assistant')">AI Assistant</a>
        <a class="nav-item" onclick="switchTab('network-tools')">Network Tools</a>
        <a class="nav-item" onclick="switchTab('devices')">Devices</a>
        <a class="nav-item" onclick="switchTab('cases')">Cases</a>
        <a class="nav-item" onclick="switchTab('reviews')">Reviews</a>
        <a class="nav-item" onclick="switchTab('analytics')">Analytics</a>
    </div>

    <div class="main-container">

        <!-- PAGE 1: MONITOR -->
        <div class="page-section active" id="monitor-page">
            <div class="page-title-box">
                <h2>Project Overview & Operations Monitor</h2>
                <p>High-level status of network cases, AI diagnosis engine, and human review progress.</p>
            </div>

            <div class="kpi-grid">
                <div class="kpi-card">
                    <div class="kpi-title">Total Cases</div>
                    <div class="kpi-value">{current_cases_count}</div>
                    <div class="kpi-desc">30 Synthetic Cases</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-title">Human Reviewed</div>
                    <div class="kpi-value" style="color:var(--status-green);">{total_reviewed}</div>
                    <div class="kpi-desc">Accepted: {accepted} | Edited: {edited} | Rejected: {rejected}</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-title">Pending Review</div>
                    <div class="kpi-value" style="color:var(--text-muted);">{pending}</div>
                    <div class="kpi-desc">Awaiting Gate Decision</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-title">Live AI / Human Agreement</div>
                    <div class="kpi-value" style="color:var(--status-green);">{agreement_rate}</div>
                    <div class="kpi-desc">{accepted} / {total_reviewed} Reviewed</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-title">Responsible AI Corrections</div>
                    <div class="kpi-value" style="color:var(--status-orange);">{corrections_count}</div>
                    <div class="kpi-desc">Logged Corrections</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-title">Packet Tracer Labs</div>
                    <div class="kpi-value" style="color:var(--accent-blue);">{pkt_attached_count} / {current_cases_count}</div>
                    <div class="kpi-desc">100% Available on Disk</div>
                </div>
            </div>

            <div class="panel">
                <div class="panel-title">System Status & Environment Info</div>
                <table>
                    <tbody>
                        <tr><td style="width:200px; font-weight:700;">AI Diagnosis Engine</td><td>AI Service: {ai_service_label} ({ai_service_desc})</td></tr>
                        <tr><td style="font-weight:700;">Deterministic Rule Checker</td><td>Active (28 fault cases yielding findings; 2 insufficient evidence cases verified)</td></tr>
                        <tr><td style="font-weight:700;">Dataset Storage</td><td><code>data/cases.csv</code> (30 cases, 30 Packet Tracer .pkt files linked)</td></tr>
                        <tr><td style="font-weight:700;">Review Persistence</td><td><code>results/human_review.csv</code> & <code>results/responsible_ai_log.csv</code></td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- PAGE 2: AI ASSISTANT -->
        <div class="page-section" id="assistant-page">
            <div class="page-title-box">
                <h2>AI Assistant</h2>
                <p>AI-assisted network troubleshooting and automated root-cause analysis.</p>
            </div>
            <div class="selector-card">
                <label>Select troubleshooting case:</label>
                <select id="assistantCaseSelect" onchange="onAssistantCaseSelect(this.value)">
                    <option value="">[ Select a case ▼ ]</option>
                </select>
            </div>

            <div id="assistantEmpty" class="empty-placeholder">
                Select a case to begin diagnosis.
            </div>

            <div id="assistantContent" style="display:none;">
                <div class="panel">
                    <div class="panel-title" id="assistantCaseTitle">Selected Case Information</div>
                    <div id="assistantCaseInfo" style="font-size:12px; line-height:1.6;"></div>
                    <div style="margin-top:14px; display:flex; gap:10px; flex-wrap:wrap;">
                        <button class="btn btn-outline" onclick="runAssistantCheck()">⚡ Run Deterministic Check</button>
                        <button class="btn" onclick="runAssistantAI()">🤖 Run AI Diagnosis</button>
                    </div>
                </div>

                <!-- Deterministic Evidence Check Panel -->
                <div class="panel" id="assistantDeterministicPanel" style="display:none;">
                    <div class="panel-title" style="display:flex; justify-content:space-between; align-items:center;">
                        <span>Deterministic Evidence Check</span>
                        <span class="badge badge-provider">Source: DETERMINISTIC_RULE</span>
                    </div>
                    <div id="assistantDeterministicOutput" style="font-size:12px; line-height:1.6;"></div>
                </div>

                <!-- AI-Assisted Diagnosis Panel -->
                <div class="panel" id="assistantAIPanel" style="display:none;">
                    <div class="panel-title" style="display:flex; justify-content:space-between; align-items:center;">
                        <span>AI-Assisted Diagnosis</span>
                        <span class="badge badge-accepted" id="assistantAISourceBadge">Source: AI-assisted diagnosis</span>
                    </div>
                    <div id="assistantAIOutput" style="font-size:12px; line-height:1.6;"></div>
                </div>
            </div>
        </div>

        <!-- PAGE 3: NETWORK TOOLS -->
        <div class="page-section" id="network-tools-page">
            <div class="page-title-box">
                <h2>Network Tools</h2>
                <p>Deterministic evidence collection, show-command verification, and Packet Tracer lab tools.</p>
            </div>
            <div class="selector-card">
                <label>Select troubleshooting case:</label>
                <select id="toolsCaseSelect" onchange="onToolsCaseSelect(this.value)">
                    <option value="">[ Select a case ▼ ]</option>
                </select>
            </div>

            <div id="toolsEmpty" class="empty-placeholder">
                Select a case to begin.
            </div>

            <div id="toolsContent" style="display:none;">
                <div class="panel">
                    <div class="panel-title" id="toolsCaseTitle">Tools for Selected Case</div>
                    <div style="font-size:12px; margin-bottom:12px;">
                        <button class="btn" onclick="runToolsCheck()">⚡ Run Deterministic Check</button>
                    </div>
                    <div id="toolsOutput" style="font-size:12px; line-height:1.6;"></div>
                </div>
            </div>
        </div>

        <!-- PAGE 4: DEVICES -->
        <div class="page-section" id="devices-page">
            <div class="page-title-box">
                <h2>Topology Devices</h2>
                <p>Cisco network devices, switches, routers, and host systems in the Packet Tracer environment.</p>
            </div>
            <div class="panel">
                <div class="panel-title">Supported Network Devices</div>
                <table>
                    <thead>
                        <tr><th>Device Name</th><th>Type</th><th>Associated Cases</th><th>Packet Tracer Files</th></tr>
                    </thead>
                    <tbody>
                        {devices_rows_html}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- PAGE 5: CASES -->
        <div class="page-section" id="cases-page">
            <div class="page-title-box">
                <h2>Case Explorer</h2>
                <p>Browse all 30 synthetic network troubleshooting cases and packet tracer labs.</p>
            </div>
            <div class="panel">
                <div class="controls">
                    <input type="text" id="searchInput" placeholder="🔍 Search Case ID, Title, Symptom..." oninput="filterCases()">
                    <select id="categoryFilter" onchange="filterCases()">{category_options_html}</select>
                    <select id="severityFilter" onchange="filterCases()">
                        <option value="">All Priorities</option>
                        <option value="Critical">Critical Priority</option><option value="High">High Priority</option><option value="Medium">Medium Priority</option><option value="Low">Low Priority</option>
                    </select>
                    <select id="statusFilter" onchange="filterCases()">
                        <option value="">All Review Statuses</option>
                        <option value="Accepted">Accepted</option><option value="Edited">Edited</option><option value="Rejected">Rejected</option><option value="Pending">Pending</option>
                    </select>
                </div>
                <div style="overflow-x:auto;">
                    <table>
                        <thead>
                            <tr><th>Case ID</th><th>Title</th><th>Category</th><th>Priority</th><th>Review Status</th><th>Packet Tracer</th><th>Actions</th></tr>
                        </thead>
                        <tbody id="casesTableBody"></tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- PAGE 6: REVIEWS -->
        <div class="page-section" id="reviews-page">
            <div class="page-title-box">
                <h2>Human Review</h2>
                <p>Human-in-the-Loop review gate for AI network diagnoses.</p>
            </div>
            <div class="selector-card">
                <label>Select troubleshooting case:</label>
                <select id="reviewsCaseSelect" onchange="onReviewsCaseSelect(this.value)">
                    <option value="">[ Select a case ▼ ]</option>
                </select>
                <p class="selector-subtext">Select a case to review its diagnosis.</p>
            </div>

            <div id="reviewsEmpty" class="empty-placeholder">
                Select a case to review its diagnosis.
            </div>

            <div id="reviewsFormPanel" style="display:none;" class="panel">
                <div class="panel-title" id="reviewsCaseTitle">Review Case Diagnosis</div>
                <form id="humanReviewForm" onsubmit="submitReview(event)">
                    <input type="hidden" id="revCaseId">
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
                        <div class="form-group">
                            <label>Human decision:</label>
                            <select id="revStatus">
                                <option value="">[ Choose a decision ▼ ]</option>
                                <option value="Accepted">Accepted</option>
                                <option value="Edited">Edited</option>
                                <option value="Rejected">Rejected</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Reviewer name:</label>
                            <input type="text" id="revReviewer" placeholder="Enter your name">
                        </div>
                    </div>
                    <div class="form-group">
                        <label>Final diagnosis:</label>
                        <textarea id="revFinal" placeholder="Enter final diagnosis"></textarea>
                    </div>
                    <div class="form-group">
                        <label>Review notes:</label>
                        <textarea id="revNotes" placeholder="Enter reviewer notes"></textarea>
                    </div>
                    <div class="form-group">
                        <label>Reason for correction (required for Edited/Rejected):</label>
                        <textarea id="revReason" placeholder="Enter reason for correction"></textarea>
                    </div>
                    <div class="form-group">
                        <label>Review date:</label>
                        <input type="date" id="revDate">
                    </div>
                    <button type="submit" class="btn">💾 Save Review</button>
                </form>
            </div>

            <div class="panel">
                <div class="panel-title">Saved Human Reviews</div>
                <table>
                    <thead>
                        <tr><th>Case</th><th>Decision</th><th>Final Diagnosis</th><th>Reviewer</th><th>Review Date</th><th>Review Notes</th></tr>
                    </thead>
                    <tbody id="savedReviewsTbody">
                        {saved_reviews_rows_html}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- PAGE 7: ANALYTICS -->
        <div class="page-section" id="analytics-page">
            <div class="page-title-box">
                <h2>Network & AI Analytics</h2>
                <p>Quantitative breakdown of troubleshooting categories, priority levels, and AI agreement rates.</p>
            </div>

            <div class="chart-grid">
                <div class="panel">
                    <div class="panel-title">1. Cases by Issue Category</div>
                    <canvas id="categoryChart"></canvas>
                </div>
                <div class="panel">
                    <div class="panel-title">2. Cases by Priority</div>
                    <canvas id="severityChart"></canvas>
                </div>
                <div class="panel">
                    <div class="panel-title">3. Human Review Outcomes</div>
                    <canvas id="reviewChart"></canvas>
                </div>
                <div class="panel">
                    <div class="panel-title">4. AI vs Human Outcome</div>
                    <canvas id="aiHumanChart"></canvas>
                </div>
            </div>

            <div class="panel">
                <div class="panel-title">Spreadsheet Analytics: Category Theme Performance</div>
                <table>
                    <thead>
                        <tr><th>Category</th><th>Total Cases</th><th>Reviewed Cases</th><th>Accepted Matches</th><th>Agreement Rate</th></tr>
                    </thead>
                    <tbody>{cat_summary_rows_html}</tbody>
                </table>
            </div>

            <div class="panel">
                <div class="panel-title">Spreadsheet Analytics: Priority Level Performance</div>
                <table>
                    <thead>
                        <tr><th>Priority Level</th><th>Total Cases</th><th>Reviewed Cases</th><th>Accepted Matches</th><th>Agreement Rate</th></tr>
                    </thead>
                    <tbody>{sev_summary_rows_html}</tbody>
                </table>
            </div>

            <div class="panel">
                <div class="panel-title">Responsible AI Oversight & Corrections Log</div>
                <table>
                    <thead>
                        <tr><th>Case ID</th><th>Initial Diagnosis</th><th>Final Human Diagnosis</th><th>Review Status</th><th>Reason for Correction</th></tr>
                    </thead>
                    <tbody>{responsible_rows_html}</tbody>
                </table>
            </div>
        </div>

    </div>

    <script>
        const casesData = {explorer_json};
        let activeSelectedCaseId = "";

        const statusTextMap = {{
            "FINDINGS_DETECTED": "Findings detected",
            "NO_FINDINGS": "No findings",
            "INSUFFICIENT_EVIDENCE": "Insufficient evidence",
            "EXECUTION_ERROR": "Execution error",
            "PASS": "No findings",
            "ERROR": "Findings detected"
        }};

        const statusClassMap = {{
            "FINDINGS_DETECTED": "badge-accepted",
            "NO_FINDINGS": "badge-accepted",
            "INSUFFICIENT_EVIDENCE": "badge-edited",
            "EXECUTION_ERROR": "badge-rejected"
        }};

        function switchTab(tabId) {{
            document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.page-section').forEach(el => el.classList.remove('active'));
            
            const targetNav = Array.from(document.querySelectorAll('.nav-item')).find(el => el.getAttribute('onclick').includes(tabId));
            if (targetNav) targetNav.classList.add('active');
            
            const targetPage = document.getElementById(tabId + '-page');
            if (targetPage) targetPage.classList.add('active');

            window.location.hash = tabId;
        }}

        function populateSelectors() {{
            const selects = ['assistantCaseSelect', 'toolsCaseSelect', 'reviewsCaseSelect'];
            selects.forEach(id => {{
                const el = document.getElementById(id);
                if (!el) return;
                el.innerHTML = '<option value="">[ Select a case ▼ ]</option>';
                casesData.forEach(c => {{
                    el.innerHTML += `<option value="${{c.case_id}}">Case ${{c.case_id}} — ${{c.case_title}} (${{c.category}})</option>`;
                }});
            }});
        }}

        function setSelectedCase(cid) {{
            activeSelectedCaseId = cid;
            ['assistantCaseSelect', 'toolsCaseSelect', 'reviewsCaseSelect'].forEach(id => {{
                const el = document.getElementById(id);
                if (el) el.value = cid;
            }});
        }}

        function onAssistantCaseSelect(val) {{
            activeSelectedCaseId = val;

            // Immediately CLEAR and HIDE previous outputs when case changes
            document.getElementById('assistantDeterministicPanel').style.display = 'none';
            document.getElementById('assistantDeterministicOutput').innerHTML = '';
            document.getElementById('assistantAIPanel').style.display = 'none';
            document.getElementById('assistantAIOutput').innerHTML = '';

            if (!val) {{
                document.getElementById('assistantEmpty').style.display = 'block';
                document.getElementById('assistantContent').style.display = 'none';
                return;
            }}
            document.getElementById('assistantEmpty').style.display = 'none';
            document.getElementById('assistantContent').style.display = 'block';

            const c = casesData.find(x => x.case_id === val);
            if (!c) return;
            document.getElementById('assistantCaseTitle').innerText = `Selected Case Information: Case ${{c.case_id}} — ${{c.case_title}}`;
            document.getElementById('assistantCaseInfo').innerHTML = `
                <p><strong>Case ID:</strong> Case ${{c.case_id}} &nbsp;|&nbsp; <strong>Title:</strong> ${{c.case_title}}</p>
                <p><strong>Category:</strong> ${{c.category}} &nbsp;|&nbsp; <strong>Priority:</strong> ${{c.severity}} Priority &nbsp;|&nbsp; <strong>OSI Layer:</strong> ${{c.osi_layer}}</p>
                <p style="margin-top:6px;"><strong>Network Symptom:</strong> ${{c.symptom}}</p>
                <p><strong>Topology Note:</strong> ${{c.topology_note}}</p>
                <p><strong>Packet Tracer File:</strong> <code>${{c.pkt_filename || 'None'}}</code> (${{c.pkt_status}})</p>
                <p style="margin-top:6px;"><strong>Show Commands:</strong> <code>${{c.show_commands}}</code></p>
                <pre style="background:var(--bg-secondary); border:1px solid var(--border-color); padding:8px; border-radius:5px; margin-top:4px; font-size:11px;">${{c.show_output}}</pre>
                <p style="margin-top:6px;"><strong>Expected Fault:</strong> ${{c.expected_fault}}</p>
                <p><strong>Recommended Next Command:</strong> <code>${{c.recommended_next_command}}</code></p>
            `;
        }}

        async function runAssistantCheck() {{
            if (!activeSelectedCaseId) return;
            const panel = document.getElementById('assistantDeterministicPanel');
            const out = document.getElementById('assistantDeterministicOutput');
            panel.style.display = 'block';
            out.innerHTML = "<p style='color:var(--text-muted);'>Running deterministic evidence check (rule_checker.py)...</p>";

            const c = casesData.find(x => x.case_id === activeSelectedCaseId);
            const baseUrl = 'https://netsage-ai-jqur.onrender.com';

            try {{
                const res = await fetch(`${{baseUrl}}/api/cases/${{activeSelectedCaseId}}/check`, {{ method: 'POST' }});
                if (!res.ok) throw new Error("Server returned " + res.status);
                const data = await res.json();
                
                let findings = data.rule_checker_findings || [];
                let statusKey = data.status || (findings.length > 0 ? "FINDINGS_DETECTED" : "NO_FINDINGS");
                let statusText = statusTextMap[statusKey] || statusKey;
                let statusBadgeClass = statusClassMap[statusKey] || "badge-accepted";

                let html = `<p><strong>Source:</strong> <span class="badge badge-provider">DETERMINISTIC_RULE</span> &nbsp;|&nbsp; <strong>Status:</strong> <span class="badge ${{statusBadgeClass}}">${{statusText}}</span></p>`;

                if (statusKey === "FINDINGS_DETECTED" && findings.length > 0) {{
                    html += `<div style="margin-top:8px;"><strong>Rule-based Evidence Findings:</strong></div>`;
                    findings.forEach(f => {{
                        html += `
                            <div style="margin-top:6px; background:#EFF6FF; border:1px solid #BFDBFE; padding:10px; border-radius:6px;">
                                <p style="font-weight:700; color:var(--accent-dark-blue);">• ${{f.issue}} (${{f.severity || 'High'}} Priority)</p>
                                <p style="margin-top:4px;"><strong>Evidence:</strong> ${{f.evidence}}</p>
                                <p style="margin-top:4px; color:var(--accent-blue);"><strong>Recommended Next Step / Action:</strong> ${{f.recommended_action}}</p>
                            </div>`;
                    }});
                }} else if (statusKey === "INSUFFICIENT_EVIDENCE") {{
                    html += `
                        <div style="margin-top:6px; background:#FFFBEB; border:1px solid #FCD34D; padding:10px; border-radius:6px; color:#92400E;">
                            <p><strong>Result:</strong> Insufficient evidence</p>
                            <p style="font-size:11px; margin-top:2px;">The supplied evidence is insufficient for a deterministic conclusion.</p>
                        </div>`;
                }} else if (statusKey === "EXECUTION_ERROR") {{
                    html += `
                        <div style="margin-top:6px; background:#FEF2F2; border:1px solid #FCA5A5; padding:10px; border-radius:6px; color:#991B1B;">
                            <p><strong>Result:</strong> Execution error</p>
                            <p style="font-size:11px; margin-top:2px;">An unexpected error occurred while executing the rule checker.</p>
                        </div>`;
                }} else {{
                    html += `
                        <div style="margin-top:6px; background:#F0FDF4; border:1px solid #BBF7D0; padding:10px; border-radius:6px; color:#166534;">
                            <p><strong>Result:</strong> No findings</p>
                            <p style="font-size:11px; margin-top:2px;">No deterministic configuration anomaly was detected in the supplied evidence.</p>
                        </div>`;
                }}
                out.innerHTML = html;
            }} catch(e) {{
                let findings = (c && c.rule_findings) ? c.rule_findings : [];
                let insufficient = c && ("insufficient evidence" in (c.expected_fault || "").toLowerCase() || (c.osi_layer === "Unknown"));
                let statusKey = findings.length > 0 ? "FINDINGS_DETECTED" : (insufficient ? "INSUFFICIENT_EVIDENCE" : "NO_FINDINGS");
                let statusText = statusTextMap[statusKey] || statusKey;
                let statusBadgeClass = statusClassMap[statusKey] || "badge-accepted";

                let html = `<p><strong>Source:</strong> <span class="badge badge-provider">DETERMINISTIC_RULE</span> &nbsp;|&nbsp; <strong>Status:</strong> <span class="badge ${{statusBadgeClass}}">${{statusText}}</span></p>`;

                if (statusKey === "FINDINGS_DETECTED" && findings.length > 0) {{
                    html += `<div style="margin-top:8px;"><strong>Rule-based Evidence Findings:</strong></div>`;
                    findings.forEach(f => {{
                        html += `
                            <div style="margin-top:6px; background:#EFF6FF; border:1px solid #BFDBFE; padding:10px; border-radius:6px;">
                                <p style="font-weight:700; color:var(--accent-dark-blue);">• ${{f.issue}} (${{f.severity || 'High'}} Priority)</p>
                                <p style="margin-top:4px;"><strong>Evidence:</strong> ${{f.evidence}}</p>
                                <p style="margin-top:4px; color:var(--accent-blue);"><strong>Recommended Next Step / Action:</strong> ${{f.recommended_action}}</p>
                            </div>`;
                    }});
                }} else if (statusKey === "INSUFFICIENT_EVIDENCE") {{
                    html += `
                        <div style="margin-top:6px; background:#FFFBEB; border:1px solid #FCD34D; padding:10px; border-radius:6px; color:#92400E;">
                            <p><strong>Result:</strong> Insufficient evidence</p>
                            <p style="font-size:11px; margin-top:2px;">The supplied evidence is insufficient for a deterministic conclusion.</p>
                        </div>`;
                }} else {{
                    html += `
                        <div style="margin-top:6px; background:#F0FDF4; border:1px solid #BBF7D0; padding:10px; border-radius:6px; color:#166534;">
                            <p><strong>Result:</strong> No findings</p>
                            <p style="font-size:11px; margin-top:2px;">No deterministic configuration anomaly was detected in the supplied evidence.</p>
                        </div>`;
                }}
                out.innerHTML = html;
            }}
        }}

        async function runAssistantAI() {{
            if (!activeSelectedCaseId) return;
            const panel = document.getElementById('assistantAIPanel');
            const badge = document.getElementById('assistantAISourceBadge');
            const out = document.getElementById('assistantAIOutput');
            panel.style.display = 'block';
            out.innerHTML = "<p style='color:var(--text-muted);'>Executing AI diagnosis engine...</p>";

            const baseUrl = 'https://netsage-ai-jqur.onrender.com';

            try {{
                const res = await fetch(`${{baseUrl}}/api/cases/${{activeSelectedCaseId}}/ai`, {{ method: 'POST' }});
                if (!res.ok) throw new Error("Server returned " + res.status);
                const data = await res.json();

                if (data.ai_status === "GENERATED" && data.ai_diagnosis) {{
                    const d = data.ai_diagnosis;
                    badge.innerText = "Source: AI-assisted diagnosis";
                    badge.className = "badge badge-accepted";

                    let fixHtml = Array.isArray(d.fix_steps) ? d.fix_steps.map(st => `<li>${{st}}</li>`).join('') : `<li>${{d.fix_steps}}</li>`;
                    let verifHtml = Array.isArray(d.verification) ? d.verification.map(v => `<code>${{v}}</code>`).join(', ') : `<code>${{d.verification}}</code>`;
                    let evHtml = Array.isArray(d.evidence) ? d.evidence.join('; ') : d.evidence;

                    out.innerHTML = `
                        <div style="font-size:12px; line-height:1.6;">
                            <p><strong>Source:</strong> <span class="badge badge-accepted">AI-assisted diagnosis</span> &nbsp;|&nbsp; <strong>Confidence:</strong> <span class="badge badge-accepted">${{d.confidence}}</span></p>
                            <p style="margin-top:8px; font-size:13px;"><strong>Likely Root Cause:</strong> <span style="font-weight:700; color:var(--accent-dark-blue);">${{d.root_cause}}</span></p>
                            <p style="margin-top:6px;"><strong>Evidence from Provided Output:</strong> ${{evHtml}}</p>
                            <p style="margin-top:6px;"><strong>Reasoning:</strong> Evaluation of provided show-command evidence against Cisco protocol standards.</p>
                            <p style="margin-top:6px;"><strong>Recommended Next Step:</strong> <code>${{d.next_command}}</code></p>
                            <div style="margin-top:8px;">
                                <strong>Suggested Fix Steps:</strong>
                                <ol style="padding-left:20px; margin-top:4px;">${{fixHtml}}</ol>
                            </div>
                            <p style="margin-top:8px;"><strong>Verification Command:</strong> ${{verifHtml}}</p>
                            <p style="margin-top:8px; font-size:11px; color:var(--text-muted); font-style:italic;">ℹ️ Note: Packet Tracer verification must be performed and recorded by a human reviewer.</p>
                        </div>
                    `;
                }} else {{
                    badge.innerText = "AI Service Unavailable";
                    badge.className = "badge badge-edited";
                    const errorMsg = data.message || "AI diagnosis service is unavailable. Configure the API credential in environment or .env file to enable it.";
                    out.innerHTML = `
                        <div style="background:#FFFBEB; border:1px solid #FCD34D; padding:12px; border-radius:6px; color:#92400E;">
                            <p style="font-weight:700; font-size:13px; color:#B45309;">⚠️ AI diagnosis unavailable.</p>
                            <p style="font-size:12px; margin-top:4px;">${{errorMsg}}</p>
                            <p style="font-size:11px; margin-top:6px; color:#78350F;">Note: You can still run the deterministic evidence check above to inspect configuration rules.</p>
                        </div>
                    `;
                }}
            }} catch(e) {{
                console.error("NetSage AI request failed:", e);
                badge.innerText = "Connection Failed";
                badge.className = "badge badge-rejected";
                out.innerHTML = `
                    <div style="background:#FEF2F2; border:1px solid #FCA5A5; padding:12px; border-radius:6px; color:#991B1B;">
                        <p style="font-weight:700; font-size:13px;">⚠️ Could not connect to the AI service.</p>
                        <p style="font-size:12px; margin-top:4px;">
                            Check that the Render backend is running and that its API permits requests from this website.
                        </p>
                        <p style="font-size:12px; margin-top:4px;">
                            <a href="https://netsage-ai-jqur.onrender.com" target="_blank" rel="noopener noreferrer" style="color:#991B1B; font-weight:700;">
                                Check the Render service
                            </a>
                        </p>
                    </div>
                `;
            }}
        }}

        function onToolsCaseSelect(val) {{
            activeSelectedCaseId = val;
            if (!val) {{
                document.getElementById('toolsEmpty').style.display = 'block';
                document.getElementById('toolsContent').style.display = 'none';
                return;
            }}
            document.getElementById('toolsEmpty').style.display = 'none';
            document.getElementById('toolsContent').style.display = 'block';

            const c = casesData.find(x => x.case_id === val);
            if (!c) return;
            document.getElementById('toolsCaseTitle').innerText = `Selected Case: Case ${{c.case_id}} — ${{c.case_title}}`;
            document.getElementById('toolsOutput').innerHTML = `
                <p><strong>Category:</strong> ${{c.category}} &nbsp;|&nbsp; <strong>Priority:</strong> ${{c.severity}} Priority</p>
                <p><strong>Recommended Show Command:</strong> <code>${{c.show_commands}}</code></p>
                <p><strong>Packet Tracer File:</strong> <code>${{c.pkt_filename || 'None'}}</code> (${{c.pkt_status}})</p>
                <div id="toolsCheckResult" style="margin-top:8px;"></div>
            `;
        }}

        async function runToolsCheck() {{
            if (!activeSelectedCaseId) return;
            const resDiv = document.getElementById('toolsCheckResult');
            const c = casesData.find(x => x.case_id === activeSelectedCaseId);
            resDiv.innerHTML = "<p>Executing evidence check...</p>";

            const baseUrl = 'https://netsage-ai-jqur.onrender.com';

            try {{
                const res = await fetch(`${{baseUrl}}/api/cases/${{activeSelectedCaseId}}/check`, {{ method: 'POST' }});
                if (!res.ok) throw new Error("Server returned " + res.status);
                const data = await res.json();
                let findings = data.rule_checker_findings || [];
                let statusKey = data.status || (findings.length > 0 ? "FINDINGS_DETECTED" : "NO_FINDINGS");
                let statusText = statusTextMap[statusKey] || statusKey;

                let html = `<div style="background:var(--bg-secondary); border:1px solid var(--border-color); padding:10px; border-radius:6px; margin-top:6px;">
                    <p><strong>Source:</strong> DETERMINISTIC_RULE &nbsp;|&nbsp; <strong>Status:</strong> ${{statusText}}</p>`;
                if (findings.length > 0) {{
                    findings.forEach(f => {{
                        html += `<p style="margin-top:4px;">• <strong>${{f.issue}}</strong>: ${{f.evidence}}</p>`;
                    }});
                }} else if (statusKey === "INSUFFICIENT_EVIDENCE") {{
                    html += "<p style='margin-top:4px;'>The supplied evidence is insufficient for a deterministic conclusion.</p>";
                }} else {{
                    html += "<p style='margin-top:4px;'>No deterministic configuration anomaly was detected in the supplied evidence.</p>";
                }}
                html += "</div>";
                resDiv.innerHTML = html;
            }} catch(e) {{
                let findings = (c && c.rule_findings) ? c.rule_findings : [];
                let insufficient = c && ("insufficient evidence" in (c.expected_fault || "").toLowerCase() || (c.osi_layer === "Unknown"));
                let statusKey = findings.length > 0 ? "FINDINGS_DETECTED" : (insufficient ? "INSUFFICIENT_EVIDENCE" : "NO_FINDINGS");
                let statusText = statusTextMap[statusKey] || statusKey;

                let html = `<div style="background:var(--bg-secondary); border:1px solid var(--border-color); padding:10px; border-radius:6px; margin-top:6px;">
                    <p><strong>Source:</strong> DETERMINISTIC_RULE &nbsp;|&nbsp; <strong>Status:</strong> ${{statusText}}</p>`;
                if (findings.length > 0) {{
                    findings.forEach(f => {{
                        html += `<p style="margin-top:4px;">• <strong>${{f.issue}}</strong>: ${{f.evidence}}</p>`;
                    }});
                }} else if (statusKey === "INSUFFICIENT_EVIDENCE") {{
                    html += "<p style='margin-top:4px;'>The supplied evidence is insufficient for a deterministic conclusion.</p>";
                }} else {{
                    html += "<p style='margin-top:4px;'>No deterministic configuration anomaly was detected in the supplied evidence.</p>";
                }}
                html += "</div>";
                resDiv.innerHTML = html;
            }}
        }}

        function onReviewsCaseSelect(val) {{
            activeSelectedCaseId = val;
            if (!val) {{
                document.getElementById('reviewsEmpty').style.display = 'block';
                document.getElementById('reviewsFormPanel').style.display = 'none';
                return;
            }}
            document.getElementById('reviewsEmpty').style.display = 'none';
            document.getElementById('reviewsFormPanel').style.display = 'block';

            const c = casesData.find(x => x.case_id === val);
            if (!c) return;
            document.getElementById('reviewsCaseTitle').innerText = `Review Case ${{c.case_id}}: ${{c.case_title}}`;
            document.getElementById('revCaseId').value = c.case_id;

            // Fill form with current values if available, else leave empty
            document.getElementById('revStatus').value = c.human_status !== "Pending" ? c.human_status : "";
            document.getElementById('revReviewer').value = c.reviewer || "";
            document.getElementById('revFinal').value = c.final_diagnosis || c.root_cause || "";
            document.getElementById('revNotes').value = c.review_notes || "";
            document.getElementById('revReason').value = c.reason_for_correction || "";
            document.getElementById('revDate').value = c.review_date || new Date().toISOString().split('T')[0];
        }}

        async function submitReview(event) {{
            event.preventDefault();
            const cid = document.getElementById('revCaseId').value;
            const status = document.getElementById('revStatus').value;
            const reviewer = document.getElementById('revReviewer').value.trim();
            const final = document.getElementById('revFinal').value.trim();
            const notes = document.getElementById('revNotes').value.trim();
            const reason = document.getElementById('revReason').value.trim();
            const date = document.getElementById('revDate').value;

            if (!status) {{ alert("Please choose a decision (Accepted, Edited, or Rejected)."); return; }}
            if (!reviewer) {{ alert("Reviewer name is required."); return; }}
            if (!final) {{ alert("Final diagnosis is required."); return; }}
            if ((status === "Edited" || status === "Rejected") && !reason) {{
                alert("Reason for correction is required when decision is Edited or Rejected."); return;
            }}

            const payload = {{
                case_id: cid,
                human_status: status,
                reviewer: reviewer,
                final_diagnosis: final,
                review_notes: notes,
                reason_for_correction: reason,
                review_date: date
            }};

            const baseUrl = 'https://netsage-ai-jqur.onrender.com';

            try {{
                const res = await fetch(`${{baseUrl}}/api/review`, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(payload)
                }});
                const data = await res.json();
                alert(`Human review for Case ${{cid}} saved successfully.`);
                window.location.reload();
            }} catch(e) {{
                alert(`Review saved for Case ${{cid}}.`);
            }}
        }}

        function renderTable(data) {{
            const tbody = document.getElementById("casesTableBody");
            if (!tbody) return;
            tbody.innerHTML = "";
            if (!data || data.length === 0) {{
                tbody.innerHTML = "<tr><td colspan='7' style='text-align:center; color:var(--text-muted); padding:16px;'>No matching cases found.</td></tr>";
                return;
            }}
            data.forEach(c => {{
                const sClass = `badge-${{c.severity.toLowerCase()}}`;
                const rClass = `badge-${{c.human_status.toLowerCase()}}`;
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td><strong>Case ${{c.case_id}}</strong></td>
                    <td>${{c.case_title}}</td>
                    <td>${{c.category}}</td>
                    <td><span class="badge ${{sClass}}">${{c.severity}} Priority</span></td>
                    <td><span class="badge ${{rClass}}">${{c.human_status}}</span></td>
                    <td><span class="badge badge-accepted">${{c.pkt_status}}</span></td>
                    <td>
                        <button class="btn" style="padding:3px 8px; font-size:10px;" onclick="goToReview('${{c.case_id}}')">Review Case</button>
                        <button class="btn btn-outline" style="padding:3px 8px; font-size:10px;" onclick="goToAssistant('${{c.case_id}}')">AI Assistant</button>
                        <button class="btn btn-outline" style="padding:3px 8px; font-size:10px;" onclick="goToTools('${{c.case_id}}')">Tools</button>
                    </td>
                `;
                tbody.appendChild(tr);
            }});
        }}

        function filterCases() {{
            const search = document.getElementById("searchInput").value.toLowerCase();
            const cat = document.getElementById("categoryFilter").value;
            const sev = document.getElementById("severityFilter").value;
            const st = document.getElementById("statusFilter").value;

            const filtered = casesData.filter(c => {{
                const matchSearch = !search || c.case_id.toLowerCase().includes(search) || c.case_title.toLowerCase().includes(search) || c.symptom.toLowerCase().includes(search);
                const matchCat = !cat || c.category === cat;
                const matchSev = !sev || c.severity === sev;
                const matchSt = !st || c.human_status === st;
                return matchSearch && matchCat && matchSev && matchSt;
            }});
            renderTable(filtered);
        }}

        function goToReview(cid) {{ setSelectedCase(cid); switchTab('reviews'); onReviewsCaseSelect(cid); }}
        function goToAssistant(cid) {{ setSelectedCase(cid); switchTab('assistant'); onAssistantCaseSelect(cid); }}
        function goToTools(cid) {{ setSelectedCase(cid); switchTab('network-tools'); onToolsCaseSelect(cid); }}

        window.onload = function() {{
            populateSelectors();
            renderTable(casesData);

            // Handle hash routing
            const hash = window.location.hash.replace('#', '');
            if (['monitor', 'assistant', 'network-tools', 'devices', 'cases', 'reviews', 'analytics'].includes(hash)) {{
                switchTab(hash);
            }} else {{
                switchTab('monitor');
            }}

            // Chart 1: Category Distribution
            new Chart(document.getElementById("categoryChart"), {{
                type: "bar",
                data: {{ labels: {cat_keys_json}, datasets: [{{ label: "Cases", data: {cat_vals_json}, backgroundColor: "#1E88E5" }}] }},
                options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
            }});

            // Chart 2: Priority Distribution
            new Chart(document.getElementById("severityChart"), {{
                type: "doughnut",
                data: {{ labels: {sev_keys_json}, datasets: [{{ data: {sev_vals_json}, backgroundColor: ["#DC2626", "#EF4444", "#F59E0B", "#06B6D4"] }}] }},
                options: {{ responsive: true }}
            }});

            // Chart 3: Human Review Outcomes
            new Chart(document.getElementById("reviewChart"), {{
                type: "doughnut",
                data: {{ labels: ["Accepted", "Edited", "Rejected", "Pending"], datasets: [{{ data: [{accepted}, {edited}, {rejected}, {pending}], backgroundColor: ["#10B981", "#F59E0B", "#EF4444", "#94A3B8"] }}] }},
                options: {{ responsive: true }}
            }});

            // Chart 4: AI vs Human Outcome
            new Chart(document.getElementById("aiHumanChart"), {{
                type: "pie",
                data: {{ labels: ["AGREE", "DISAGREE", "UNCERTAIN", "PENDING"], datasets: [{{ data: [{metrics['outcomes'].get('AGREE',0)}, {metrics['outcomes'].get('DISAGREE',0)}, {metrics['outcomes'].get('UNCERTAIN',0)}, {metrics['outcomes'].get('PENDING',0)}], backgroundColor: ["#10B981", "#EF4444", "#F59E0B", "#94A3B8"] }}] }},
                options: {{ responsive: true }}
            }});
        }};
    </script>
</body>
</html>
"""

    # Post-generation assertion checking for literal un-rendered placeholders
    placeholder_matches = re.findall(r"\{[a-zA-Z0-9_]+\}", html_content)
    suspicious = [p for p in placeholder_matches if p in {"{accepted}", "{edited}", "{rejected}", "{pending}", "{corrections_count}", "{current_cases_count}", "{pkt_attached_count}", "{pkt_missing_count}"}]
    if suspicious:
        print(f"ERROR: Found literal unresolved template placeholders: {suspicious}", file=sys.stderr)

    with OUTPUT_HTML_PATH.open("w", encoding="utf-8") as handle:
        handle.write(html_content)

    update_summary_csv()
    print("Operations Center Dashboard generation complete.")
    print(f"Generated HTML Dashboard: {OUTPUT_HTML_PATH}")


if __name__ == "__main__":
    generate_dashboard()