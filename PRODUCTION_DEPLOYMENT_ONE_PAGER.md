# Production Deployment One-Pager

## Objective

Deploy the Sales Order Schedule Troubleshooter to production with:

- Enterprise authentication via Okta
- Role-based access control (RBAC)
- Snowflake as the production data source
- Scalable, secure deployment options including Dataiku

## Recommended Production Pattern

Use a **Hybrid deployment model**:

- **Dataiku** for upstream data orchestration, enrichment, and publishing curated datasets
- **FastAPI application tier** for UI/API, RBAC enforcement, and low-latency user interactions
- **Snowflake** as governed system of record and shared data contract layer

This keeps data pipeline responsibilities separate from runtime user experience responsibilities.

## Core Architecture

- **Identity**: Okta OIDC (Authorization Code + PKCE), corporate SSO
- **Authorization**: RBAC in app layer with Okta group-to-role mapping
- **Data**: Snowflake secure views for sales orders, schedules, supply, allocations, deliveries, BOP, and substitutions
- **Operations**: centralized logs, metrics, traces, and audit records
- **Channels**: standard query UI and chatbot UX under the same security/audit controls

## RBAC Roles (Initial)

- **Admin**: platform/role configuration and operations
- **Analyst**: full troubleshooting and investigation features
- **Support**: troubleshooting + support handoff actions
- **ReadOnly/Audit**: view-only access for governance/audit use

## Security Controls (Must-Have)

- Vault/KMS-managed secrets, credential rotation
- TLS and secure cookies
- Private networking/allowlists
- Snowflake least-privilege service roles
- Immutable audit logging and defined retention
- Data masking/row policies where required

## Snowflake Production Design

- App reads from curated secure views (not raw landing schemas)
- Dedicated warehouse for app workload with auto-suspend/resume tuning
- Parameterized queries + pagination controls
- Data freshness SLA and lineage defined and monitored

## Deployment Options

- **Option A**: Container platform + Snowflake
- **Option B**: Managed web runtime + Snowflake
- **Option C**: Dataiku-centric runtime
- **Option D (Recommended)**: Dataiku pipelines + dedicated FastAPI serving tier + Snowflake

## Reliability and Operations

- Multi-instance deployment, health checks, autoscaling
- Blue/green or canary rollout with rollback gates
- SLOs on latency/error rate/query performance
- Runbooks and on-call ownership model

## Testing and Cutover

- **TUT**: reason logic, authz guards, query paths
- **FUT**: role-based UI/API flows
- **Integration**: Okta, Snowflake, Dataiku publish contracts
- **Security/Performance**: token/session tests, dependency scans, load tests
- Environments: `DEV` -> `QA` -> `UAT` -> `PRD`

## 30/60/90-Day Plan

- **0-30 days**: architecture decision, Okta setup, Snowflake contracts, secrets model
- **31-60 days**: RBAC implementation, Snowflake integration, observability and controls
- **61-90 days**: UAT/security/load, pilot rollout, production launch + hypercare

## Success Criteria

- Decision-ready architecture with approved deployment path
- RBAC + Okta integrated and validated
- Snowflake governance controls approved by security/data owners
- Production SLOs and support model in place

## Execution Reference

For rollout execution details, use `PRODUCTION_IMPLEMENTATION_STEPS.md`.
