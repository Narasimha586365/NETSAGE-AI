"""Interactive review web server for NetSage AI.

Serves the NetSage AI web application and API endpoints.
Supports CORS preflight requests so the Vercel-hosted frontend can call
the Render-hosted backend.
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
    load_cases,
    load_human_reviews,
    load_responsible_ai_log,
    calculate_all_metrics,
    run_single_case_check,
    run_single_case_ai,
    save_human_review,
)
from generate_dashboard import generate_dashboard


# The deployed frontend origin. CORS requests from this site are permitted.
# The localhost origin is included to keep local development/testing convenient.
ALLOWED_ORIGINS = {
    "https://netsage-ai-teal.vercel.app",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
}


class NetSageInteractiveHandler(BaseHTTPRequestHandler):
    def _send_cors_headers(self) -> None:
        """Add CORS headers to API responses when the origin is allowed."""
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header(
                "Access-Control-Allow-Methods",
                "GET, POST, OPTIONS",
            )
            self.send_header(
                "Access-Control-Allow-Headers",
                "Content-Type, Authorization",
            )
            self.send_header("Access-Control-Max-Age", "86400")

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._send_cors_headers()
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

    def do_OPTIONS(self) -> None:
        """Respond to browser CORS preflight requests."""
        origin = self.headers.get("Origin", "")

        if origin not in ALLOWED_ORIGINS:
            self.send_response(403)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

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
            for case in cases:
                case_id = case["case_id"]
                review = rev_map.get(case_id)
                case["human_status"] = (
                    review.get("human_status", "Pending") if review else "Pending"
                )
            self._send_json(cases)
        elif path.startswith("/api/cases/"):
            parts = [part for part in path.split("/") if part]
            if len(parts) >= 3:
                case_id = parts[2]
                cases = load_cases()
                target = next(
                    (case for case in cases if case["case_id"] == case_id),
                    None,
                )
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
        length = int(self.headers.get("Content-Length", "0"))
        body_bytes = self.rfile.read(length) if length > 0 else b"{}"

        try:
            req_data = json.loads(body_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json({"error": "Request body must be valid JSON"}, status=400)
            return

        # POST /api/cases/<case_id>/check
        if "/check" in path:
            parts = [part for part in path.split("/") if part]
            case_id = parts[2] if len(parts) >= 3 else req_data.get("case_id", "")
            result = run_single_case_check(str(case_id))
            self._send_json(result)

        # POST /api/cases/<case_id>/ai
        elif "/ai" in path:
            parts = [part for part in path.split("/") if part]
            case_id = parts[2] if len(parts) >= 3 else req_data.get("case_id", "")
            result = run_single_case_ai(str(case_id))
            self._send_json(result)

        # POST /api/review or /api/reviews
        elif path in {"/api/review", "/api/reviews"}:
            result = save_human_review(req_data)
            generate_dashboard(mode_banner="🟢 SYSTEM ONLINE")
            self._send_json(result)
        else:
            self._send_json({"error": "Endpoint not found"}, status=404)


def run_server(port: int = 8080) -> None:
    generate_dashboard(mode_banner="🟢 SYSTEM ONLINE")
    print("=== NetSage AI Interactive Review Web Server Running ===")
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
