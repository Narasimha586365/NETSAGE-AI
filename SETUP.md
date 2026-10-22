# NetSage-AI — Setup & Deployment Guide

This guide provides instructions for setting up, configuring, and verifying the **NetSage-AI** network troubleshooting system for review and submission.

---

## 1. System Requirements

- **Operating System**: Windows 10/11, Linux, or macOS
- **Python Runtime**: Python 3.10 or higher
- **Required Package**: `google-genai` (Google GenAI Python SDK)

---

## 2. Installation & Environment Setup

### Step 1: Install Dependencies

From the project root directory (`D:\NetSage-AI`), install the required SDK:

```cmd
pip install google-genai
```

### Step 2: Configure Environment Credentials Securely

1. Copy `.env.example` to `.env`:

   ```cmd
   copy .env.example .env
   ```

2. Open `.env` in a text editor and configure your API key:

   ```text
   GEMINI_API_KEY=YOUR_ACTUAL_GEMINI_API_KEY
   NETSAGE_AI_MODEL=gemini-3.5-flash-lite
   ```

> **SECURITY IMPORTANT**: Never commit `.env` containing your real API credential to version control. `.env` is excluded by `.gitignore`.

---

## 3. Verification & Execution Pipeline

Run these commands in Windows CMD or PowerShell from `D:\NetSage-AI`:

### 1. Validate Dataset Completeness & Packet Tracer Files

```cmd
python python\validate_dataset.py
```

*Verifies that all 30 troubleshooting cases are complete and all 30 `.pkt` lab files are present on disk in `packet_tracer_30-cases/`.*

### 2. Test Deterministic Cisco Rule Engine

```cmd
python python\test_rule_checker.py
```

*Audits Cisco show-command evidence across all 30 cases (28 findings detected, 2 insufficient evidence).*

### 3. Perform Dry-Run Pipeline Validation

```cmd
python python\run_diagnosis.py --dry-run
```

*Validates data flow without making live API calls or writing result files.*

### 4. Run Single-Case Analysis or Controlled Fresh API Test

```cmd
:: Test single case using cached result if available
python python\run_diagnosis.py --case 26

:: Force a fresh live API call test for Case 26
python python\run_diagnosis.py --case 26 --force
```

### 5. Execute Complete 30-Case Analysis Pipeline

```cmd
python python\run_diagnosis.py
```

*Processes all 30 cases. Uses cached diagnoses from `results/diagnosis_responses/case_XX.json` when available to prevent unnecessary API consumption.*

### 6. Regenerate NOC Operations Center Dashboard

```cmd
python python\generate_dashboard.py
```

*Updates `results/dashboard.html` with current metrics and review statuses.*

---

## 4. Interactive Web Application

To launch the local interactive web interface and NOC Operations Center:

```cmd
python python\app.py
```

Open your browser at: `http://127.0.0.1:8080`

---

## 5. Security & Submission Compliance

- **No Hardcoded Secrets**: Credentials must exist only in local environment variables or local `.env`.
- **No Secret Leakage**: API status outputs `CONFIGURED` or `NOT_CONFIGURED` without revealing key lengths or secret strings.
- **Git Exclusions**: `.env`, `*.env`, and `__pycache__/` are excluded via `.gitignore`.
