# Demonstrating a NetSage AI case

This project does not hard-code a single demo case. In the local dashboard, choose any of the 30 manually authored cases and use the same workflow.

## Before

Read the selected case symptom and topology notes. The application identifies the associated Packet Tracer file only when it exists on disk.

## Evidence

Review the supplied show-command output, expected fault, OSI layer, severity, recommended command, and Packet Tracer notes. These are case inputs, not live telemetry.

## Deterministic finding

Click **Run deterministic check**. Its output is labelled `DETERMINISTIC_RULE`; it is not an AI response.

## AI assistance

Click **Run AI diagnosis** only when a configured AI API is available.

- If an API response returns valid structured JSON, the stored source is `AI_API`.
- Otherwise the interface shows **AI model unavailable. No AI response was generated.**

No manually authored case text or deterministic finding is silently converted into AI output.

## Human review

Open **Reviews**, choose Accepted, Edited, or Rejected, then enter reviewer name, final diagnosis, and notes. For Edited or Rejected decisions, enter the reason for correction. Nothing is saved before **Save Review** is clicked.

## Packet Tracer fix and verification

After human approval, make the change manually in Cisco Packet Tracer. Run the appropriate verification command and record the result through your review process.

**Verification pending:** NetSage AI does not fabricate ping results, command output, or Packet Tracer verification.
