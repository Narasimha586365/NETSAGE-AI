"""Configurable AI diagnosis provider for NetSage AI.

Provides persistent environment loading, structured JSON diagnosis generation,
automatic rate-limit retry handling, and clean SDK configuration without AFC warnings.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

try:
    from google import genai
    from google.genai import types
    TYPES_AVAILABLE = True
except ImportError:
    try:
        from google import genai
        TYPES_AVAILABLE = False
    except ImportError:
        genai = None
        TYPES_AVAILABLE = False


ROOT = Path(__file__).resolve().parent.parent
PROMPT = ROOT / "prompts" / "diagnose_prompt.md"

REQUIRED = {
    "root_cause",
    "osi_layer",
    "confidence",
    "evidence",
    "next_command",
    "fix_steps",
    "verification",
}


def load_env() -> None:
    """Load key-value pairs from project root .env file if present, without overwriting existing environment variables."""
    env_file = ROOT / ".env"
    if env_file.is_file():
        try:
            with env_file.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass


def is_rate_limit_error(err: Exception) -> bool:
    """Check if an exception corresponds to an HTTP 429 / Rate Limit / Resource Exhausted error."""
    msg = str(err).lower()
    return any(
        kw in msg
        for kw in [
            "429",
            "resource_exhausted",
            "quota",
            "rate limit",
            "rate_limit",
            "too many requests",
        ]
    )


def extract_retry_delay(err: Exception) -> float:
    """Extract recommended retry delay from error message, adding a safety margin."""
    msg = str(err)
    match = re.search(r"retry\s+(?:after|in)\s+(\d+(?:\.\d+)?)\s*s?", msg, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1)) + 2.0
        except ValueError:
            pass
    return 10.0


class AIDiagnosisProvider:
    """Generate NetSage diagnoses using configured API integration."""

    def __init__(self) -> None:
        load_env()
        self.key = os.getenv("GEMINI_API_KEY", "").strip()
        self.model = os.getenv(
            "NETSAGE_AI_MODEL",
            "gemini-3.5-flash-lite",
        ).strip()

        self.client = None

        if self.key and genai is not None:
            try:
                self.client = genai.Client(api_key=self.key)
            except Exception:
                self.client = None

    def get_provider_info(self) -> dict[str, str]:
        """Return provider configuration information without exposing API keys."""

        if not self.key:
            return {
                "status": "NOT_CONFIGURED",
                "diagnosis_source": "UNAVAILABLE",
                "message": (
                    "AI diagnosis service is unavailable. "
                    "Configure GEMINI_API_KEY in environment or .env file to enable it."
                ),
                "model": "Not configured",
            }

        if self.client is None:
            return {
                "status": "NOT_CONFIGURED",
                "diagnosis_source": "UNAVAILABLE",
                "message": (
                    "AI client could not be initialized. "
                    "Check the API library installation and configuration."
                ),
                "model": "Configured Engine",
            }

        return {
            "status": "CONFIGURED",
            "diagnosis_source": "AI-assisted diagnosis",
            "message": (
                "AI service is configured and ready. "
                "A result is stored only after a successful structured response."
            ),
            "model": "Configured Engine",
        }

    def render_prompt(
        self,
        case: dict[str, str],
        findings: list[dict[str, Any]],
    ) -> str:
        """Build the diagnosis prompt from the project template."""

        text = PROMPT.read_text(encoding="utf-8")

        replacements = {
            "symptom": case.get("symptom", "Not provided"),
            "topology_note": case.get(
                "topology_note",
                "Not provided",
            ),
            "show_output": case.get(
                "show_output",
                "Not provided",
            ),
        }

        for key, value in replacements.items():
            text = text.replace(
                "{" + key + "}",
                value,
            )

        appendix = {
            "category": case.get("category"),
            "concept": case.get("concept"),
            "severity": case.get("severity"),
            "expected_fault": case.get("expected_fault"),
            "recommended_next_command": case.get(
                "recommended_next_command"
            ),
            "deterministic_rule_findings": findings,
        }

        return (
            text
            + "\n\nAdditional supplied case evidence "
            "(do not infer beyond it):\n"
            + json.dumps(
                appendix,
                indent=2,
                ensure_ascii=False,
            )
            + "\n\n"
            "Return ONLY a valid JSON object. "
            "Do not use Markdown code fences."
        )

    def parse_diagnosis(
        self,
        raw: str,
    ) -> dict[str, Any] | None:
        """Validate and parse the structured AI response."""

        if not raw:
            return None

        raw = raw.strip()

        if raw.startswith("```json"):
            raw = raw[len("```json"):].strip()

        if raw.startswith("```"):
            raw = raw[len("```"):].strip()

        if raw.endswith("```"):
            raw = raw[:-3].strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict):
            return None

        if not REQUIRED.issubset(data):
            return None

        if data.get("confidence") not in {
            "High",
            "Medium",
            "Low",
        }:
            return None

        for key in (
            "evidence",
            "fix_steps",
            "verification",
        ):
            if not isinstance(data.get(key), list):
                return None

        return {
            key: data[key]
            for key in REQUIRED
        }

    def generate_diagnosis(
        self,
        case: dict[str, str],
        findings: list[dict[str, Any]],
        max_retries: int = 4,
        on_retry: Callable[[str, int, float, str], None] | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Generate one diagnosis using API client with rate-limit handling and clean SDK config."""

        if not self.key:
            return (
                None,
                "AI diagnosis service is unavailable. "
                "API credential is not configured.",
            )

        if self.client is None:
            return (
                None,
                "AI client could not be initialized.",
            )

        prompt = self.render_prompt(
            case,
            findings,
        )

        case_id = case.get("case_id", "Unknown")
        attempt = 0

        while attempt <= max_retries:
            try:
                if TYPES_AVAILABLE:
                    afc_config = types.AutomaticFunctionCallingConfig(disable=True)
                    config_obj = types.GenerateContentConfig(
                        temperature=0.2,
                        response_mime_type="application/json",
                        automatic_function_calling=afc_config,
                    )
                else:
                    config_obj = {
                        "temperature": 0.2,
                        "response_mime_type": "application/json",
                    }

                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config_obj,
                )

                raw = response.text or ""
                diagnosis = self.parse_diagnosis(raw)

                if not diagnosis:
                    return (
                        None,
                        "AI service returned an invalid structured diagnosis.",
                    )

                diagnosis.update(
                    {
                        "diagnosis_source": "AI-assisted diagnosis",
                        "provider": "AI Service",
                        "model": "Configured Engine",
                    }
                )

                return diagnosis, None

            except Exception as err:
                error_text = str(err)
                if self.key and self.key in error_text:
                    error_text = error_text.replace(self.key, "[REDACTED]")

                if is_rate_limit_error(err) and attempt < max_retries:
                    attempt += 1
                    delay = extract_retry_delay(err)
                    if on_retry:
                        on_retry(case_id, attempt, delay, error_text)
                    else:
                        print(
                            f"Case {case_id}: Rate limit reached. "
                            f"Waiting {int(delay)} seconds before retry..."
                        )
                    time.sleep(delay)
                    continue

                return (
                    None,
                    "AI service API request failed: " + error_text,
                )

        return (
            None,
            f"AI service rate limit exceeded after {max_retries} retries.",
        )