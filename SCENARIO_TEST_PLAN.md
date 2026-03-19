# Scenario Catalog and Test Plan

## 1) Purpose

This document defines the end-to-end scenario set for the Sales Order Schedule Troubleshooter POC and the test plan for each scenario.

Each scenario includes:
- **TUT** (Technical Unit Tests): rule/logic validation in Python modules.
- **FUT** (Functional Unit Tests): user-facing behavior in web UI and API responses.
- **Integration checks**: POC API contracts plus future SAP integration points (OData/RFC/IDoc and SAP GUI/ABAP debug traceability).

---

## 2) Test Scope and Environments

- **POC app**: FastAPI + Jinja2 + pandas CSV datasets.
- **Primary URLs**:
  - Web: `http://127.0.0.1:8000/`
  - API docs: `http://127.0.0.1:8000/docs`
  - OpenAPI endpoints: `/api/*`
- **Key datasets**:
  - `sales_orders.csv`, `sales_order_items.csv`, `sales_order_schedules.csv`
  - `stock_supply.csv`, `planned_orders.csv`, `allocations.csv`
  - `deliveries.csv`, `bop_logs.csv`, `plant_substitutions.csv`

Representative order examples from test data are included below.

---

## 3) Scenario Matrix (Quick View)

| ID | Scenario | Example Orders | Core Expected Outcome |
|---|---|---|---|
| S01 | Full stock confirmation on request date | `5000000001`-`5000000008` | `CONFIRMED_FROM_STOCK`, on-time |
| S02 | Partial stock + planned order, pushed out | `5000000009`-`5000000014` | `PARTIAL_STOCK_PLANNED_ORDER`, delayed explanation present |
| S03 | Planned-order-led confirmation, pushed out | `5000000015`-`5000000019`, `5000000050` | `CONFIRMED_FROM_PLANNED_ORDER`, delayed explanation present |
| S04 | Allocation exhausted | `5000000023`, `5000000025` | `NO_SCHEDULE_ALLOCATION_EXHAUSTED` |
| S05 | No supply no schedule | `5000000042`-`5000000045` | `NO_SCHEDULE_NO_SUPPLY` |
| S06 | Multi-factor block + no supply | `5000000039` | `NO_SCHEDULE_MULTI_FACTOR`, contributing reasons include block + no supply |
| S07 | Plant substitution with alternate supply | `5000000038` | `CONFIRMED_WITH_PLANT_SUBSTITUTION` |
| S08 | Mixed outcomes in one order (multi-part) | `5000000046`, `5000000048` | One item confirmed, one unscheduled; parts differentiated |
| S09 | Snapshot reason clarity for pushed-out lines | `5000000011`, `5000000015` | explanation states why delay occurs despite stock/planned supply |
| S10 | BOP constraint (no BOP_FAILED as final reason) | `5000000042` etc. | no `NO_SCHEDULE_BOP_FAILED` / `BOP_FAILED` in final outputs |
| S11 | Filter: not fully scheduled on request date | Home/API filter flag | only impacted orders returned |
| S12 | Pagination and navigation controls | Home list pages | `10/25/50` rows, `« ‹ › »` controls |
| S13 | Dataset status drill-down | `/datasets/{name}` | read-only raw table per dataset |
| S14 | Snapshot support email workflow | Snapshot order page | `Email PLPC Support` mailto with readable details |
| S15 | Docs usability | `/docs` | visible Home link on right side |
| S16 | Render deploy runtime compatibility | Render build/deploy logs | service runs on Python 3.12.8 and health check passes |
| S17 | Query-detail consistency and state retention | `5000000039` and filtered list flows | exact SO behavior, preserved query context, same detail format, back returns same state |
| S18 | Production migration readiness | Snowflake/Okta/RBAC integration checklist | app can run without sample CSV data and enforces role-based access |

---

## 4) Detailed Test Plan per Scenario

## S01 - Full Stock Confirmation on Request Date
- **Objective**: Validate on-time confirmations when stock fully covers requested quantity.
- **TUT**
  - Validate `determine_reason()` returns `CONFIRMED_FROM_STOCK`.
  - Assert no delayed/unscheduled flags for qualifying rows.
- **FUT**
  - Open `/orders/5000000001?snapshot_date=<latest>`.
  - Confirm reason label/code and equal requested/scheduled date.
- **Integration checks**
  - API: `GET /api/troubleshoot/5000000001?mode=snapshot`
  - Future SAP: `VA03`, `CO09`, `MD04`; ABAP debug in ATP determination call stack.
- **Expected**: On-time confirmation with stock-driven rationale.

## S02 - Partial Stock + Planned Order (Pushed Out)
- **Objective**: Confirm delayed schedules include explicit push-out explanation.
- **TUT**
  - Validate delayed rows include `SCHEDULE_PUSHED_OUT` contributing reason.
  - Validate reason text explains requested vs delayed timing.
- **FUT**
  - Check `/orders/5000000009?snapshot_date=<latest>`.
  - Confirm delayed row highlighting and clear explanation for date push-out.
- **Integration checks**
  - API: `GET /api/troubleshoot/5000000009`
  - Future SAP: compare against `VBEP` schedule lines and planned receipt timing (`PLAF`/MRP).
- **Expected**: Supply exists but date is delayed with explicit timing reason.

## S03 - Planned-Order-Led Confirmation (Pushed Out)
- **Objective**: Explain why planned-order-backed confirmations can still be late.
- **TUT**
  - Validate `CONFIRMED_FROM_PLANNED_ORDER` is returned when planned supply covers quantity.
  - Validate push-out explanation logic when schedule date > request date.
- **FUT**
  - Check `/orders/5000000015?snapshot_date=<latest>` and `/orders/5000000050?snapshot_date=<latest>`.
- **Integration checks**
  - API response reason text includes delayed explanation.
  - Future SAP: `MD04`, planned order availability dates vs request dates.
- **Expected**: Confirmation present but delayed with human-readable cause.

## S04 - Allocation Exhaustion
- **Objective**: Ensure exhausted allocation blocks scheduling even when supply is present.
- **TUT**
  - Validate allocation precedence and exhausted branch.
  - Assert `NO_SCHEDULE_ALLOCATION_EXHAUSTED`.
- **FUT**
  - Open `/orders/5000000023?mode=snapshot`.
  - Verify unscheduled highlight and contributing allocation reason.
- **Integration checks**
  - API: `GET /api/troubleshoot/5000000023?mode=snapshot`
  - Future SAP: allocation object checks, plus ABAP breakpoints in allocation selection logic.
- **Expected**: No schedule due to allocation cap exhaustion.

## S05 - No Supply -> No Schedule
- **Objective**: Validate no-supply outcome and unscheduled display behavior.
- **TUT**
  - Assert `NO_SCHEDULE_NO_SUPPLY` for no stock/planned coverage.
- **FUT**
  - Open `/orders/5000000042?mode=snapshot`.
  - Verify red row highlight and no schedule date.
- **Integration checks**
  - API payload shows no-supply reason and supporting contributors.
  - Future SAP: stock check (`MARD`), schedule check (`VBEP`) and MRP availability.
- **Expected**: Unscheduled with no-supply explanation.

## S06 - Multi-Factor: Delivery Block + No Supply
- **Objective**: Validate multi-factor reason and contributing reasons.
- **TUT**
  - Validate `NO_SCHEDULE_MULTI_FACTOR` path.
  - Validate normalized delivery-state contributors (no conflicts).
- **FUT**
  - Open `/orders/5000000039?mode=snapshot`.
  - Check contributors include `DELIVERY_BLOCKED` + `NO_SUPPLY_SOURCE_PLANT`.
- **Integration checks**
  - API includes both factors; no mutually exclusive delivery states.
  - Future SAP: `VL03N` + delivery block fields + ATP supply.
- **Expected**: Combined blocker reason rendered clearly.

## S07 - Plant Substitution with Alternate Supply
- **Objective**: Validate substitution logic when source plant lacks supply.
- **TUT**
  - Assert `CONFIRMED_WITH_PLANT_SUBSTITUTION` when alternate supply closes gap.
- **FUT**
  - Open `/orders/5000000038?mode=snapshot`.
  - Verify substitution-related contributor and reason text.
- **Integration checks**
  - API evidence includes substitution context.
  - Future SAP: substitution rule CDS/table chain + alternate plant availability.
- **Expected**: Confirmed via substitution path.

## S08 - Mixed Outcomes in One Order
- **Objective**: Ensure item-level divergence is handled correctly.
- **TUT**
  - Validate one order can contain both confirmed and unscheduled lines.
  - Validate order-level part aggregation returns all unique parts.
- **FUT**
  - Open `/orders/5000000046?mode=snapshot` and `/orders/5000000048?mode=snapshot`.
  - Confirm one schedule on-time and one unscheduled in same order.
  - Confirm `Parts in order` and `Part` column values align with line items.
- **Integration checks**
  - API item/schedule drilldown endpoints align with order detail page.
  - Snapshot support email includes item/part/schedule context for each line.
- **Expected**: Accurate per-line outcomes without collapsing to a single status.

## S09 - Snapshot Reason Clarity for Pushed-Out Lines
- **Objective**: Ensure delayed schedules clearly state timing cause.
- **TUT**
  - Validate push-out explanation text distinguishes stock timing vs planned-order timing.
  - Validate explanation is aligned with primary reason code.
- **FUT**
  - Open `/orders/5000000011?snapshot_date=<latest>` and confirm stock-plus-planned timing explanation.
  - Open `/orders/5000000015?snapshot_date=<latest>` and confirm planned-order-after-request-date explanation.
- **Integration checks**
  - API: `GET /api/troubleshoot/5000000011` and `GET /api/troubleshoot/5000000015`.
- **Expected**: Human-readable explanation explicitly answers why request date was missed.

## S10 - BOP Constraint (No BOP_FAILED Final Output)
- **Objective**: Enforce business rule that BOP failed is not a final reason.
- **TUT**
  - Validate remap behavior for legacy BOP fail indicators.
- **FUT**
  - Inspect snapshot outputs for BOP-related orders.
- **Integration checks**
  - API assertions: final reasons never equal `NO_SCHEDULE_BOP_FAILED` or `BOP_FAILED`.
  - Future SAP: BOP logs in `SLG1`/job logs (`SM37`) used only as context.
- **Expected**: BOP statuses appear as context contributors only.

## S11 - Filter: Only Not Fully Scheduled on Requested Date
- **Objective**: Return only impacted orders.
- **TUT**
  - Validate `not_fully_scheduled_on_request_date_order_set()`.
- **FUT**
  - Use Home checkbox: "Only orders not fully scheduled on requested date".
  - Verify list excludes fully on-time and fully confirmed orders.
- **Integration checks**
  - API: `GET /api/sales-orders?only_not_fully_on_request_date=true`.
  - API troubleshoot query with same flag.
- **Expected**: Filtered result set contains only qualifying impacted orders.

## S12 - Pagination and Navigation
- **Objective**: Validate usability for long order lists.
- **TUT**
  - Validate page bounds and page-size capping logic (`max 50`).
- **FUT**
  - Test `10`, `25`, `50` rows/page.
  - Verify `« ‹ › »` controls top and bottom.
  - Confirm navigation preserves all filters.
- **Integration checks**
  - URL query integrity across page transitions.
- **Expected**: Predictable paging and stateful navigation.

## S13 - Dataset Raw Inspection
- **Objective**: Provide transparent read-only dataset visibility.
- **TUT**
  - Validate dataset key checks and preview payload.
- **FUT**
  - From Home, click each dataset tile.
  - Verify read-only table and row counts.
- **Integration checks**
  - `GET /datasets/{dataset_name}` returns proper pages and 404 for invalid keys.
- **Expected**: Auditable raw-data access by dataset.

## S14 - Snapshot Support Email Workflow
- **Objective**: Enable fast support handoff with readable context.
- **TUT**
  - Validate mail body formatter includes summary + schedule details.
- **FUT**
  - Snapshot mode: click `Email PLPC Support`.
  - Confirm recipient `cmayer@amd.com`, readable subject/body content.
- **Integration checks**
  - Link appears on snapshot detail pages and opens mail client with populated review payload.
- **Expected**: Human-readable prefilled support email opens correctly (grid-style rows/columns).

## S15 - API Docs Home Navigation
- **Objective**: Ensure quick return path from docs to app home.
- **TUT**
  - Validate docs wrapper route serves top bar and iframe.
- **FUT**
  - Open `/docs`, click Home (right-aligned).
- **Integration checks**
  - `/docs` and `/api-docs-internal` both accessible.
- **Expected**: Docs remain usable with explicit app navigation.

## S16 - Render Deploy Runtime Compatibility
- **Objective**: Prevent cloud deploy failures caused by incompatible Python runtime selection.
- **TUT**
  - Validate deployment config includes runtime pin in both `runtime.txt` and `render.yaml` (`PYTHON_VERSION=3.12.8`).
- **FUT**
  - Trigger deploy and confirm app serves home page and `/api/health`.
- **Integration checks**
  - Inspect Render logs to confirm Python runtime is `3.12.8` and no `pydantic-core`/`maturin` metadata-generation failure occurs.
  - If stale cache causes wrong runtime selection, run **Manual Deploy -> Clear build cache & deploy** and re-validate health.
- **Expected**: Successful build/deploy with healthy service endpoint.

## S17 - Query-Detail Consistency and List-State Retention
- **Objective**: Ensure query-based navigation and hyperlink navigation lead to the same detail experience and preserve user context.
- **TUT**
  - Validate sales-order filtering path uses exact match when `sales_order` is provided.
  - Validate source query parameters are carried into detail links.
- **FUT**
  - Enter exact SO (`5000000039`) and submit query; verify redirect opens the same detail layout as hyperlink navigation.
  - Query with combined filters (`sales_order`, `customer`, `material`, `plant`, snapshot, page/page-size), open detail, verify sidebar reflects source context.
  - Click `Back` and confirm list returns with same filters and page state.
- **Integration checks**
  - `GET /api/troubleshoot?sales_order=5000000039` returns only that order's schedules.
  - Detail route remains stable with query-context params appended.
- **Expected**: No context mismatch between query and detail; user trust and continuity are preserved.

## S18 - Production Migration Readiness (Snowflake + Okta + RBAC)
- **Objective**: Validate production implementation prerequisites and cutover readiness.
- **TUT**
  - Validate runtime can initialize with Snowflake-backed data source configuration.
  - Validate role guard checks for Admin/Analyst/Support/ReadOnly_Audit access paths.
- **FUT**
  - Validate Okta-authenticated user access to UI with role-appropriate behavior.
  - Validate unauthorized users are blocked from protected routes/actions.
  - Validate app behavior when sample CSV mode is disabled.
- **Integration checks**
  - Snowflake connectivity and least-privilege role usage (`ROLE_SO_APP_READ`).
  - Group-to-role claim mapping from Okta to app authorization.
  - Audit events captured for login, query, detail view, and support action workflows.
- **Expected**: Production dependency stack is operational and security controls are enforced.

---

## 5) Future SAP-Connected Validation Addendum

When integrating this POC with SAP S/4HANA (PS4/QS4/DS4), extend each scenario with:

- **SAP GUI checks**
  - `VA03` (order/item/schedule)
  - `CO09` (ATP situation)
  - `MD04` (stock/receipt timeline)
  - `VL03N` (delivery and block status)
  - `SM37`, `SLG1`, `ST22` (job/log/dump diagnostics)
  - `SE16N` for table-level checks (`VBAK`, `VBAP`, `VBEP`, `MARD`, `PLAF`, `LIKP`, `LIPS`)
- **ABAP debug strategy**
  - External breakpoints in ATP/allocation/BOP determination classes.
  - CDS chain verification for allocation/supply/substitution reads.
  - AMDP trace if pushdown logic is introduced.
- **Integration interfaces**
  - OData service contract validation (payload parity to POC fields).
  - RFC read/service validation for schedule evidence objects.
  - IDoc event consistency where delivery/order updates are distributed.

---

## 6) Exit Criteria

The POC scenario test cycle is complete when:

- All 18 scenarios pass TUT + FUT checks.
- API and web outputs are consistent for equivalent queries.
- No final output contains `NO_SCHEDULE_BOP_FAILED` or `BOP_FAILED`.
- Delayed stock/planned-order cases include explicit push-out explanation.
- Support handoff email is readable and complete.
