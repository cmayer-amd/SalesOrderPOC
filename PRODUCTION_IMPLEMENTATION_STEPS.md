# Production Implementation Steps

## Purpose

This document provides an execution-ready checklist for moving the Sales Order Schedule Troubleshooter from POC mode (sample CSV datasets) to production mode (Snowflake + Okta + RBAC + enterprise operations).

It complements:

- `PRODUCTION_DEPLOYMENT_DESIGN.md` (target architecture and controls)
- `PRODUCTION_DEPLOYMENT_ONE_PAGER.md` (leadership summary)

## 1) Pre-Implementation Decisions

1. Confirm production deployment model:
   - Option A/B/C/D from production design (recommended: Hybrid Option D).
2. Confirm data ownership:
   - business owner for each source domain
   - technical owner for Snowflake curation.
3. Confirm identity ownership:
   - Okta app owner
   - IAM/security approver for group mappings and policies.
4. Confirm go-live scope:
   - pilot business unit
   - geographies/plants included in phase 1.

## 2) Environment Preparation

Prepare and harden environments: `DEV`, `QA`, `UAT`, `PRD`.

- Provision runtime target for FastAPI/UI.
- Establish CI/CD with branch policies and environment promotion gates.
- Provision secrets manager (Vault/KMS) and remove plaintext credentials.
- Configure centralized logging, metrics, and alerting sink.

Deliverables:

- Environment inventory
- Access matrix
- CI/CD pipeline definition

## 3) Snowflake Data Migration (Replace Sample Datasets)

## 3.1 Create Curated Objects

Implement governed Snowflake views/tables for:

- `sales_orders`
- `sales_order_items`
- `sales_order_schedules`
- `stock_supply`
- `allocations`
- `deliveries`
- `planned_orders`
- `bop_logs`
- `plant_substitutions`

Use curated schemas and secure views; do not expose raw landing schemas to the app.

## 3.2 Data Contracts and Quality

- Define contract fields, datatypes, null-handling, and freshness SLA.
- Add quality checks:
  - key integrity (header/item/schedule)
  - duplicate detection
  - out-of-range date/quantity values.
- Publish data dictionary and lineage references.

## 3.3 Performance

- Provision dedicated app warehouse.
- Tune for:
  - parameterized query paths
  - predicate pushdown
  - pagination limits
  - auto-suspend/resume.

Acceptance criteria:

- App query latencies meet defined SLO.
- Data freshness and completeness meet SLA.

## 4) Okta Authentication Implementation

1. Register application in Okta.
2. Configure OIDC:
   - Authorization Code + PKCE
   - redirect URIs per environment
   - token/session policies.
3. Configure required claims:
   - `sub`, `email`, `name`, `preferred_username`, group/role claims.
4. Enforce secure session handling:
   - HTTP-only, secure cookies
   - strict same-site policy
   - session timeout controls.

Acceptance criteria:

- Unauthorized users cannot access protected pages/endpoints.
- Authenticated session flow works across DEV/QA/UAT/PRD.

## 5) Role-Based Security with Snowflake Roles

## 5.1 Application Roles

Use application roles:

- `Admin`
- `Analyst`
- `Support`
- `ReadOnly_Audit`

Map Okta groups to app roles at login/session issuance.

## 5.2 Snowflake Least-Privilege Roles

Create Snowflake access roles aligned to runtime needs:

- `ROLE_SO_APP_READ`
- `ROLE_SO_DATA_ENG`
- `ROLE_SO_AUDIT`

Guidelines:

- App runtime principal uses read-only role.
- No DDL privileges from app runtime.
- Apply masking and row access policies where required.

## 5.3 Authorization Enforcement

- UI-level role gating for user experience.
- API-level role checks for actual enforcement.
- Audit log each privileged action and support-handoff action.

Acceptance criteria:

- Role matrix validated with positive and negative test cases.
- Snowflake role grants reviewed and signed off by security.

## 6) Application Configuration Cutover

1. Add environment configuration for Snowflake connection and role usage.
2. Disable sample CSV loaders in production mode.
3. Keep optional local sample mode for non-production only.
4. Add startup validation:
   - auth config present
   - Snowflake connectivity
   - required datasets/views reachable.

Acceptance criteria:

- Production runtime starts without CSV dependency.
- Health checks include dependency readiness checks.

## 6.1 Chatbot Channel Readiness

- Secure chatbot API route with the same role checks as query APIs.
- Validate natural-language parsing behavior for sales order/customer/part prompts.
- Add chatbot-specific observability:
  - intent classification outcomes
  - no-result events
  - response latency and failure rates.
- Ensure chatbot responses do not bypass any data access restrictions enforced for standard APIs.

## 7) Security, Compliance, and Audit Hardening

Must-have controls:

- Secret rotation runbook and break-glass process.
- TLS enforcement and header hardening.
- Network controls (private endpoints/allowlists as applicable).
- Immutable audit logs with retention policy.
- Data classification and privacy controls.

Security tests:

- auth bypass attempts
- token/session misuse
- over-privileged role verification
- data exfiltration scenarios.

## 8) Testing and Validation Plan

## 8.1 Technical Unit Tests (TUT)

- Reason engine rule parity against POC behavior.
- Role guard unit tests.
- Snowflake query adapter tests.

## 8.2 Functional Unit Tests (FUT)

- Query, detail, pagination, highlighting behavior.
- Role-specific UI and action controls.
- Support email workflow with approval control.
- Chatbot conversational behavior and in-chat result rendering.

## 8.3 Integration and Enterprise Validation

- Okta end-to-end auth flow.
- Snowflake data access and policy enforcement.
- Optional Dataiku orchestration contract.
- SAP validation checkpoints:
  - `VA03`, `CO09`, `MD04`, `VL03N`, `SM37`, `SLG1`, `ST22`, `SE16N`
  - ABAP/CDS chain debug traceability.

## 9) Cutover and Go-Live Steps

1. Change freeze and deployment window approval.
2. Promote release artifact to PRD.
3. Execute smoke tests:
   - login
   - core query paths
   - detail page and reason trace.
4. Run monitored pilot period (hypercare).
5. Final business sign-off and transition to steady-state support.

Rollback readiness:

- previous stable artifact available
- database/object compatibility verified
- rollback communication path prepared.

## 10) Post-Go-Live Operations

Weekly:

- review auth failures and role exceptions
- review query latency and warehouse utilization
- review support workflow quality metrics.

Monthly:

- access recertification
- secrets rotation check
- dependency vulnerability review
- DR/restore exercise status review.

## 11) Frequently Missed Items (Checklist)

- [ ] Okta group lifecycle and deprovisioning process
- [ ] Snowflake cost guardrails (warehouse auto-suspend and query budget alerts)
- [ ] Data retention and purge policy alignment
- [ ] Incident severity model and on-call handoff coverage
- [ ] Audit evidence export process for compliance reviews
- [ ] UAT sign-off artifacts archived for release governance
- [ ] Support training and runbook handoff completed
