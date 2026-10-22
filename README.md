# NetSage-AI

## AI-Assisted Packet Tracer Network Troubleshooting System

NetSage-AI is a network troubleshooting platform built for Cisco Packet Tracer lab environments. It operates on evidence-first principles: network symptoms, topology notes, Packet Tracer show-command outputs, and expected faults are analyzed through a multi-stage workflow combining deterministic rule checking, structured AI diagnosis, and human review.

## Architecture & Workflow

`Deterministic Network Analysis → Structured AI Diagnosis → Human Review Gate → Final Assessment`

1. **Deterministic Rule Engine**: Inspects show-command output against Cisco network rules (VLANs, trunks, static/OSPF routes, IP subnets, default gateways, ACLs, interface states, DHCP, DNS).
2. **AI Diagnosis Engine**: Generates structured root-cause analysis using the Google Gemini API (`google-genai` SDK).
3. **Human Review Gate**: Network engineers review deterministic findings and AI output before accepting, editing, or rejecting the diagnosis.
4. **Responsible AI Logging**: Records human corrections and final assessments for system auditing.

## Local Configuration & Setup

### 1. Environment Configuration

Copy `.env.example` to `.env` in the project root:

```cmd
copy .env.example .env
```

Edit `.env` to configure your Gemini API credential:

```text
GEMINI_API_KEY=YOUR_ACTUAL_GEMINI_API_KEY
NETSAGE_AI_MODEL=gemini-3.5-flash-lite
```

*(Note: Never commit `.env` containing actual API keys to version control.)*

### 2. Launch Local Web Application

Start the local server and NOC Operations Center:

```cmd
python python\app.py
```

Open your web browser at:
`http://127.0.0.1:8080`

## Project Structure

- `data/cases.csv` — The 30 synthetic network troubleshooting cases (VLAN, Routing, IP, Gateway, DHCP, ACL, Interface, DNS).
- `packet_tracer_30-cases/` — Packet Tracer lab files referenced by the dataset.
- `prompts/diagnose_prompt.md` — Reusable structured evidence-first diagnosis prompt.
- `python/rule_checker.py` — Deterministic Cisco show-command rule evaluation engine.
- `python/ai_diagnosis.py` — Configurable Gemini API diagnosis provider with automatic rate-limit retry handling.
- `python/data_manager.py` — Shared data flow manager handling case loading, review persistence, and metrics calculations.
- `python/run_diagnosis.py` — Batch and single-case CLI pipeline runner with diagnosis caching.
- `python/generate_dashboard.py` — Generator for `results/dashboard.html` NOC Operations Center dashboard.
- `python/app.py` / `python/interactive_dashboard.py` — Local HTTP server providing REST API endpoints.
- `results/` — Saved structured diagnoses, human review records, Responsible AI log, and generated dashboard artifacts.

## CLI Command Line Verification

From `D:\NetSage-AI` in Windows CMD or PowerShell:

```cmd
:: 1. Validate dataset health and references
python python\validate_dataset.py

:: 2. Test deterministic rule engine across 30 cases
python python\test_rule_checker.py

:: 3. Run dry-run pipeline test (no API calls written)
python python\run_diagnosis.py --dry-run

:: 4. Run single-case diagnosis test
python python\run_diagnosis.py --case 23

:: 5. Run complete 30-case analysis pipeline (uses cached results when available)
python python\run_diagnosis.py

:: 6. Regenerate HTML NOC Operations Center dashboard
python python\generate_dashboard.py
```

## Responsible AI & Safety Principles

- Deterministic findings and AI diagnoses are kept clearly separated from human decisions.
- A diagnosis is marked as **PENDING** human review until an engineer explicitly reviews and saves a decision.
- Packet Tracer lab verification is human-controlled and must be physically conducted in Packet Tracer before being recorded.
- No credentials or secret keys are hardcoded in source files or displayed in console outputs.
