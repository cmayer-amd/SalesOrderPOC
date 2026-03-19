# Functional Design - SAP Sales Order Schedule Troubleshooter

## 1. Purpose

Provide a web-based troubleshooting tool that explains why SAP sales order schedules were confirmed, delayed, or left unconfirmed.

The tool supports:

- Sales order level analysis
- Line item level analysis
- Schedule line level analysis
- Multi-factor reason trace (not only a single cause)
- Snapshot-based analysis (single mode)

This is designed for S/4HANA-style ATP/AATP reasoning with AMD-oriented concepts:

- OPN-level supply checks
- Allocation hierarchy constraints
- Delivery and delivery-block impacts
- Planned order coverage
- BOP log outcomes
- Plant substitution rules

## 2. Scope

### In Scope

- Query by sales order, customer, material/part, and optional plant.
- Show schedule reasons for all matching schedules.
- Conversational chatbot query by sales order/customer/part.
- Highlight business-critical rows:
  - Unscheduled rows
  - Delayed rows (schedule date > requested date)
- Analyze snapshot state (last run / last BOP context) only.
- Provide API and web UI access.
- Support sharing via LAN URL.

### Out of Scope

- Live SAP integration (RFC/OData/IDoc runtime calls).
- Real-time database persistence.
- Authorization and role model.
- Workflow approvals or execution in SAP.

## 3. Users and Personas

- Supply chain analyst
- Order management / customer operations analyst
- ATP/BOP functional consultant
- Support engineer troubleshooting confirmation issues

## 4. Process Overview

1. User searches by sales order, customer, or material.
2. Tool returns matching schedules and reason outcomes.
3. User drills into order detail.
4. User reviews primary reason + contributing reason trace.

## 5. High-Level Architecture

### Backend

- Framework: FastAPI
- Data source: flat CSV files loaded into memory via pandas
- Core modules:
  - `app/data_loader.py`
  - `app/reason_engine.py`
  - `app/routers/api.py`
  - `app/routers/web.py`

### Frontend

- Jinja2 templates + server-rendered HTML
- CSS styling in `app/static/app.css`

### Deployment/Run Mode

- Local machine with optional LAN sharing
- Uvicorn host can run on:
  - `127.0.0.1` (local only)
  - `0.0.0.0` (shareable on network)

## 6. Data Model and Datasets

All files are in `data/`.

- `sales_orders.csv` (50 rows) - order header
- `sales_order_items.csv` (53 rows) - order item
- `sales_order_schedules.csv` (53 rows) - schedule line
- `stock_supply.csv` (35 rows) - OPN/source supply
- `allocations.csv` (20 rows) - allocation constraints
- `deliveries.csv` (6 rows) - delivery and block indicators
- `planned_orders.csv` (13 rows) - planned supply
- `bop_logs.csv` (8 rows) - BOP outcomes
- `plant_substitutions.csv` (3 rows) - substitution routing

### Key Relations

- Header -> Item -> Schedule
- Item + Header -> Allocation
- Item -> Stock/Planned supply
- Item/Schedule -> Delivery and BOP logs
- Item -> Plant substitution rule -> Alternate-plant supply

## 7. Functional Rules

## 7.1 Core Rule Families

### A. Delivery-Based

- GI posted -> delivered confirmation outcome
- Delivery exists in process -> delivery-in-process effect
- Delivery block active -> delivery-block contributing cause

### B. Source Supply (OPN / Plant / Storage)

- Full coverage by stock/planned -> confirm
- Partial coverage -> partial outcomes
- No source supply -> no-supply contributing cause

### C. Allocation Hierarchy

Priority order:

1. `CUSTOMER_SOLDTO_SHIPTO`
2. `CUSTOMER_REGION`
3. `CUSTOMER`

Outcomes:

- Active allocation with remaining quota
- Allocation exhausted -> no schedule or severe restriction

### D. BOP

- BOP run status is used as context only (`BOP_SUCCESS`, `BOP_PARTIAL` contributors).
- `BOP FAILED` is not emitted as a final business reason.
- Legacy BOP-failed indicators are remapped to non-BOP outcomes (for example, no feasible supply).

### E. Plant Substitution

- If source plant has no supply and substitution rule exists:
  - If alternate plant supply can be applied -> substitution confirmation
  - Else -> substitution pending / unresolved no-schedule outcome

## 7.2 Multi-Factor Reasoning

The engine returns:

- `reason_code` (primary)
- `reason_text`
- `contributing_reasons[]` (secondary/combined causes)

Example:

- Primary: `NO_SCHEDULE_MULTI_FACTOR`
- Contributing:
  - `DELIVERY_BLOCKED`
  - `NO_SUPPLY_SOURCE_PLANT`
  - `DELIVERY_IN_PROCESS`

## 7.3 Confirmation Guardrail

- A line must have true schedule confirmation to be labeled as confirmed:
  - `confirmed_qty >= requested_qty`
  - schedule date present
  - schedule status is not `UNCONFIRMED`
- Stock/planned/substitution availability without confirmed schedule state is not sufficient for a confirmed reason.
- If supply exists but line remains unconfirmed, reason remains no-schedule/unresolved based on constraints in the dataset row.

## 7.4 Snapshot Mode

Use saved schedule and last BOP context as historical status.

## 8. UI Functional Design

## 8.1 Home Page (`/`)

Sections:

- Dataset status counts
- Dataset status drill-down links (one per file)
- Query form (sales order, customer, material, plant)
- Rows-per-page control (`10`, `25`, `50`)
- Filtered schedule reason results table
- Sales order list table
- Chatbot link in top navigation (`/chatbot`)

Behavior:

- Query by one or more filters
- Click order number for detail page
- Click dataset tile to open read-only raw table view (`/datasets/{dataset_name}`)
- Sales-order pagination controls shown above and below list
- Pagination links preserve filter context across pages
- Main list includes `Part(s)` as aggregated materials per order
- If `sales_order` is entered, matching uses exact SO value and prioritizes SO over other text filters
- Row highlights:
  - Red = unscheduled
  - Amber = delayed (pushed out)

Pagination controls:

- `«` first page
- `‹` previous page
- `›` next page
- `»` last page

## 8.2 Order Detail (`/orders/{so}`)

Controls:

- `Snapshot (Last BOP Run)` state indicator
- `Home` and `Back` links in Schedule Analysis section
- Snapshot support action: `Email PLPC Support`

Tables:

- Snapshot columns shown
- Schedule table includes a `Part` column at line level

Panels:

- Reason Trace panel with ordered reason list
- Snapshot mail action provides prefilled, human-readable review details to PLPC support
- Order header shows `Parts in order` to represent multi-line, multi-part orders
- Left sidebar shows opened-from query filter criteria for drill-down context

## 8.3 Query-to-Detail Consistency Rules

- Detail links preserve originating query context (`sales_order`, `customer`, `material`, `plant`, readiness filter, page, page size, snapshot date).
- Querying by an exact sales order that yields one order redirects to that same detail format used by hyperlink navigation.
- The detail page sidebar reflects the same order/query context the user came from.
- `Back` navigation is expected to return to the same filtered and paged list state.
- Snapshot version selection remains consistent between list and detail flows.

## 8.4 Chatbot Page (`/chatbot`)

- Conversation-style interaction for schedule troubleshooting.
- Natural-language prompt parsing for:
  - Sales order prompts
  - Customer prompts
  - Part/material prompts
- Chat response content:
  - schedule-level fields (SO/item/schedule/part/customer/region/req/sched dates)
  - primary and contributing reasons as chips
  - in-chat status color coding:
    - red for unscheduled
    - amber for pushed-out
    - standard for on-time/confirmed

Highlights:

- Red unscheduled schedule rows
- Amber delayed schedule rows

## 9. API Functional Design

### Core Endpoints

- `GET /api/health`
- `GET /api/sales-orders`
- `GET /api/sales-orders/{so_number}`
- `GET /api/sales-orders/{so_number}/items/{item_number}`
- `GET /api/sales-orders/{so_number}/items/{item_number}/schedules/{schedule_line}`
- `GET /api/troubleshoot/{so_number}` (snapshot output)
- `GET /api/troubleshoot?sales_order=&customer=&material=&plant=`
- `POST /api/chatbot/query`

### Web Endpoints

- `GET /` home, query, and dataset status
- `GET /orders/{so_number}` order detail, snapshot mode
- `GET /datasets/{dataset_name}` read-only raw dataset inspection
- `GET /chatbot` conversational query page

### Response Expectations

- Schedule-level output includes:
  - part/material context per schedule line
  - reason code/text
  - requested/confirmed qty and dates
  - evidence blocks
  - contributing reasons
- UI labels are normalized for readability (shortened, no underscores), while API reason codes remain canonical.

## 10. Highlighting and UX Rules

- **Unscheduled row**:
  - No schedule date OR reason starts with `NO_SCHEDULE`
- **Delayed row**:
  - Schedule date exists and is later than requested date

Applied in:

- Main order list
- Filtered results
- Order detail schedule table

Header readability rule:

- Table header labels wrap only at normal break points (spaces).
- Header labels do not split inside words.

## 11. Test Data Scenario Coverage

Data includes scenarios for:

- Full stock confirmations
- Partial stock + planned orders
- Planned-only
- Allocation constraints/exhaustion
- Delivery-created flows
- No supply
- Legacy BOP-failure indicators remapped to non-BOP outcomes
- Mixed outcomes in one order
- No-allocation records
- Multi-factor (delivery block + no supply)
- Plant substitution (including substitute-plant supply available)

## 12. Testing Strategy for Handoff

### TUT (Technical Unit Tests)

- Reason precedence tests
- Allocation hierarchy matching tests
- Multi-factor composition tests
- Snapshot reason and precedence tests

### FUT (Functional Unit Tests)

- Query behavior by SO/customer/material
- Drilldown consistency (header -> item -> schedule)
- Highlight behavior:
  - unscheduled
  - delayed
- Snapshot detail and reason-trace behavior

### Integration-Style Checks

- API contract checks for key endpoints
- Data integrity checks across CSV relationships
- Network accessibility verification for shared URL mode

## 13. Operations and Sharing Notes

- One-command run (project root):
  - `powershell -ExecutionPolicy Bypass -File .\scripts\start-app.ps1`
- One-command safe redeploy:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\restart-app.ps1`
- LAN share URL format:
  - `http://<host-ip>:8000`
- Firewall/network policy may be required for coworker access.

### Production Transition References

For production migration beyond this POC design, use:

- `PRODUCTION_DEPLOYMENT_DESIGN.md` for target architecture, security model, and deployment options.
- `PRODUCTION_DEPLOYMENT_ONE_PAGER.md` for executive summary and decision framing.
- `PRODUCTION_IMPLEMENTATION_STEPS.md` for execution checklist:
  - Snowflake cutover (replace sample datasets)
  - Okta authentication onboarding
  - RBAC enforcement with Snowflake least-privilege roles
  - hardening, validation, and go-live steps.
- Cloud-hosted share URL (Render):
  - `https://sales-order-poc.onrender.com/`

Render deployment/runtime compatibility rule:

- Render service must run Python `3.12.8` for dependency compatibility (`pydantic-core` wheel path).
- Runtime pin is configured in both:
  - `runtime.txt`
  - `render.yaml` (`PYTHON_VERSION=3.12.8`)
- If a deploy attempts Python `3.14`, run **Manual Deploy -> Clear build cache & deploy** in Render.

### BOP Failure Handling Constraint

BOP FAILED is not treated as a valid business error condition in this tool. Any legacy BOP-failed indicators are remapped to non-BOP outcomes (for example, no feasible supply), and UI/API outputs must not emit `NO_SCHEDULE_BOP_FAILED` or `BOP_FAILED` as final reasons.

### Snapshot Review Mail Constraint

The snapshot page includes a support-mail action labeled `Email PLPC Support`, which opens a prefilled email to `cmayer@amd.com`. The email body is intentionally human-readable and includes both an order summary and schedule-line detail rows (including item, part, and schedule references) for support review.

### Documentation in App Constraint

Project documents are exposed in-app under `/documents` and rendered from repository markdown files. Any update to `README.md`, `FUNCTIONAL_DESIGN.md`, `SCENARIO_TEST_PLAN.md`, or `POC_MANAGEMENT_ONE_PAGER.md` must be visible through this route after redeploy/restart.

## 14. Backout / Revert Strategy

Changes were designed to be easy to reverse:

- Snapshot reason logic isolated in `app/reason_engine.py`
- Query-context sidebar and detail layout isolated in `app/templates/order_detail.html`
- Snapshot troubleshoot endpoint behavior isolated in `app/routers/api.py`
- New dataset `plant_substitutions.csv` is additive only

To back out:

1. Re-enable alternate mode controls in `app/templates/order_detail.html`.
2. Reintroduce mode branching in `app/routers/web.py` and `app/routers/api.py`.
3. Keep baseline query and snapshot troubleshooting features unchanged.

## 15. Handoff Checklist

- [ ] Confirm coworker can access shared URL.
- [ ] Validate snapshot output on at least 3 delayed orders.
- [ ] Validate unscheduled and delayed highlights on home and detail pages.
- [ ] Validate multi-factor reason trace for blocked/no-supply order.
- [ ] Validate plant substitution scenario.

