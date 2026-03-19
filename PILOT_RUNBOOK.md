# Support Email AI Pilot Runbook

## Scope

- Pilot objective: reduce support drafting effort while preserving quality and compliance.
- Channels: shared support mailbox routed through `/api/support-automation/*`.
- User populations:
  - Requestors (email senders)
  - Admin reviewers (human approval gate)
- This runbook is pilot-specific; production migration steps are documented in `PRODUCTION_IMPLEMENTATION_STEPS.md`.

## Guardrails

- In-tenant processing only (Microsoft-native + Azure-hosted AI path).
- Citation-first response requirement for all AI draft outputs.
- Automatic escalation conditions:
  - Confidence below configured threshold
  - Policy-sensitive keywords (legal/HR/security)
  - Missing citations
- No outbound auto-send; admin action is mandatory.

## Pilot Execution Steps

1. Validate trigger mode (`power_automate` recommended) through `GET /api/support-automation/config`.
2. Confirm indexed knowledge set using:
   - `GET /api/support-automation/knowledge-scope`
   - `POST /api/support-automation/knowledge-scope/reindex`
3. Process pilot batch emails via `POST /api/support-automation/ingest-email`.
4. Work review queue from `GET /api/support-automation/review-queue`.
5. Approve, edit, or escalate with `POST /api/support-automation/review/{draft_id}`.
6. Monitor `GET /api/support-automation/metrics` and `GET /api/support-automation/audit-log`.

## KPI Targets

- Draft acceptance rate (`approved_sent` + `edited_sent`) >= 0.80.
- Average confidence >= 0.60 for accepted drafts.
- Escalation rate <= 0.25 after initial tuning.
- 100% sent messages with reviewer attribution and send timestamp in audit log.

## Tuning Loop

- Weekly retrieval review:
  - Check low-confidence drafts and update scope coverage.
  - Refine chunking/document hygiene in source content.
- Prompt quality loop:
  - Compare original draft vs edited outbound text.
  - Improve response framing and citation wording.
- Operational loop:
  - Reindex when new documents are published.
  - Review policy keyword list for false positives and missed categories.

## Rollback/Fallback

- If quality degrades, pause ingestion and move to manual-only handling.
- Keep audit logs and draft records for post-incident analysis.
