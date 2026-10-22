"""Entry point for NetSage AI Interactive Dashboard Web App.

Run using:
python python/app.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "python"))

from interactive_dashboard import run_server

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    run_server(port=port)
