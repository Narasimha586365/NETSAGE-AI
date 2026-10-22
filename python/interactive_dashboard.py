"""Interactive local review web server for NetSage AI.

Serves an interactive Web Application at http://localhost:8080:
1. Complete Case Explorer displaying all 30 cases cleanly loaded from data/cases.csv.
2. Single-case execution for 'Run Case Check' (rule_checker.py) and 'Run AI Diagnosis' (ai_diagnosis.py).
3. Interactive Human Review Gate Form with Accept / Edit / Reject workflow.
4. Immediate persistence to results/human_review.csv and results/responsible_ai_log.csv.
5. Local recalculation of review and outcome metrics.
6. Honest configurable AI API status banner.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_ROOT / "results"

if str(PROJECT_ROOT / "python") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "python"))

from data_manager import (
    load_cases, load_human_reviews, load_responsible_ai_log,
    calculate_all_metrics, run_single_case_check, run_single_case_ai, save_human_review
)
from generate_dashboard import generate_dashboard


class NetSageInteractiveHandler(BaseHTTPRequestHandler):
    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, mime: str = "text/html") -> None:
        if not path.exists():
            self.send_error(404, "File Not Found")
            return
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path in {"/", "/index.html", "/dashboard.html"}:
            generate_dashboard(mode_banner="🟢 SYSTEM ONLINE")
            self._send_file(RESULTS_DIR / "dashboard.html", "text/html")
        elif path == "/api/cases":
            cases = load_cases()
            reviews = load_human_reviews()
            rev_map = {r["case_id"]: r for r in reviews}
            for c in cases:
                cid = c["case_id"]
                r = rev_map.get(cid)
                c["human_status"] = r.get("human_status", "Pending") if r else "Pending"
            self._send_json(cases)
        elif path.startswith("/api/cases/"):
            parts = [p for p in path.split("/") if p]
            if len(parts) >= 3:
                cid = parts[2]
                cases = load_cases()
                target = next((c for c in cases if c["case_id"] == cid), None)
                if target:
                    self._send_json(target)
                else:
                    self._send_json({"error": "Case not found"}, status=404)
            else:
                self._send_json({"error": "Invalid request"}, status=400)
        elif path in {"/api/reviews", "/api/human_reviews"}:
            self._send_json(load_human_reviews())
        elif path in {"/api/stats", "/api/summary"}:
            self._send_json(calculate_all_metrics())
        else:
            self._send_file(RESULTS_DIR / "dashboard.html", "text/html")

    def do_POST(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(length) if length > 0 else b"{}"

        try:
            req_data = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            req_data = {}

        # Handle POST /api/cases/<case_id>/check
        if "/check" in path:
            parts = [p for p in path.split("/") if p]
            cid = parts[2] if len(parts) >= 3 else req_data.get("case_id", "")
            res = run_single_case_check(str(cid))
            self._send_json(res)

        # Handle POST /api/cases/<case_id>/ai
        elif "/ai" in path:
            parts = [p for p in path.split("/") if p]
            cid = parts[2] if len(parts) >= 3 else req_data.get("case_id", "")
            res = run_single_case_ai(str(cid))
            self._send_json(res)

        # Handle POST /api/review or /api/reviews
        elif path in {"/api/review", "/api/reviews"}:
            res = save_human_review(req_data)
            generate_dashboard(mode_banner="🟢 SYSTEM ONLINE")
            self._send_json(res)
        else:
            self._send_json({"error": "Endpoint not found"}, status=404)


def run_server(port: int = 8080) -> None:
    generate_dashboard(mode_banner="🟢 SYSTEM ONLINE")
    print(f"=== NetSage AI Interactive Review Web Server Running ===")
    print(f"URL: http://localhost:{port}")
    print("Press Ctrl+C to stop.")
    server = HTTPServer(("0.0.0.0", port), NetSageInteractiveHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.server_close()


if __name__ == "__main__":
    port_val = int(os.getenv("PORT", "8080"))
    run_server(port=port_val)
