# Sales Order Troubleshooter (FastAPI Starter)

Starter FastAPI scaffold for SAP sales order schedule-date troubleshooting.

## What this starter includes

- API endpoints for:
  - sales order search
  - sales order detail
  - item/schedule drill-down
  - schedule reason troubleshooting
- Web UI pages using Jinja2 templates
- Deterministic reason engine with precedence:
  1. Delivery status
  2. OPN-level stock/supply
  3. Allocation hierarchy
  4. Planned orders
  5. BOP logs
- CSV data loader for flat files
- Dataset inspection pages for each source file (`/datasets/{dataset_name}`)
- Sales-order pagination with configurable page size (`10`, `25`, `50`)
- Snapshot review mail action (`Email PLPC Support`) with prefilled schedule details
- Part visibility at both order and schedule levels (including multi-part orders)

## Project structure

```text
app/
  main.py
  data_loader.py
  reason_engine.py
  routers/
    api.py
    web.py
  templates/
    base.html
    index.html
    order_detail.html
    dataset_view.html
  static/
    app.css
data/
  README.md
scripts/
  start-app.ps1
  restart-app.ps1
requirements.txt
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Data files expected in `data/`

- `sales_orders.csv`
- `sales_order_items.csv`
- `sales_order_schedules.csv`
- `stock_supply.csv`
- `allocations.csv`
- `deliveries.csv`
- `planned_orders.csv`
- `bop_logs.csv`
- `plant_substitutions.csv`

You can copy the generated test data from:

`C:\Users\cmayer\.cursor\skills\sap-so-schedule-troubleshooter\test-data\`

## Run (one-command)

Use these from the project root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-app.ps1
```

If a stale process exists on port 8000, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restart-app.ps1
```

Open:

- Web UI: `http://127.0.0.1:8000/`
- OpenAPI: `http://127.0.0.1:8000/docs`
- Dataset raw view example: `http://127.0.0.1:8000/datasets/sales_orders`

## Run in GitHub Codespaces

1. Open your repo on GitHub:
   - `https://github.com/cmayer-amd/SalesOrderPOC`
2. Click **Code** -> **Codespaces** -> **Create codespace on main**.
3. Wait for the dev container to finish setup (dependencies are installed automatically from `requirements.txt`).
4. In the Codespace terminal, run:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

5. Open the forwarded port `8000` URL in the Codespace browser preview.

Notes:
- `.devcontainer/devcontainer.json` is included to preconfigure Python 3.12 and port forwarding.
- The app runs with Linux shell commands in Codespaces (not the Windows PowerShell scripts).

## Run from GitHub with a shareable URL (Render)

GitHub repository URLs host source code, not a running FastAPI process.  
To run the app from your GitHub repo and share a public app URL:

1. Open [Render](https://render.com/) and sign in.
2. Click **New** -> **Blueprint**.
3. Connect GitHub repo: `cmayer-amd/SalesOrderPOC`.
4. Render will detect `render.yaml` and create web service `sales-order-poc`.
5. Deploy and open the generated URL (for example: `https://sales-order-poc.onrender.com`).

Notes:
- The app health check is configured at `/api/health`.
- Every push to `main` auto-deploys by default (`autoDeploy: true` in `render.yaml`).

## Dataset inspection (read-only)

- The **Dataset Status** tiles on `/` are clickable.
- Each tile opens a read-only raw-data table for that file.
- Supported dataset keys:
  - `sales_orders`
  - `sales_order_items`
  - `sales_order_schedules`
  - `stock_supply`
  - `allocations`
  - `deliveries`
  - `planned_orders`
  - `bop_logs`
  - `plant_substitutions`

## Sales order pagination

- Sales order list is paginated with rows-per-page options (`10`, `25`, `50`).
- Pagination controls are available above and below the table.
- Navigation controls use icons:
  - `«` first page
  - `‹` previous page
  - `›` next page
  - `»` last page
- Pagination preserves search filters (`sales_order`, `customer`, `material`, `plant`).

## Part visibility

- Main Sales Orders list includes a `Part(s)` column.
- `Part(s)` shows all unique materials in each sales order (comma-separated).
- Order detail Schedule Analysis includes a `Part` column per line item.
- Order detail header shows `Parts in order` for quick multi-line/multi-part context.

## Order detail navigation and support mail

- In the **Schedule Analysis** section on order detail pages:
  - `Home` and `Back` links are always shown.
  - In snapshot mode only, `Email PLPC Support` is shown on the right side.
- `Email PLPC Support` opens an email to `cmayer@amd.com` with:
  - order summary (customer, region, counts)
  - readable schedule-by-schedule reason details
  - item + part + schedule context for each line
  - contributing reason codes where present

## Header readability rule

- Table headers are configured to wrap only at normal break points (spaces).
- Header text does not split inside words.

## Documentation artifacts

- Functional design: `FUNCTIONAL_DESIGN.md`
- Management summary: `POC_MANAGEMENT_ONE_PAGER.md`

## Current-state feasibility semantics

- In current check mode, the API/UI return `can_meet_requested_date_now`.
- This is true only when:
  - current reason is not a `NO_SCHEDULE*` outcome, and
  - current schedule date is on/before requested date.
- For comparison behavior, current check projects a schedule date to requested date when current confirmed quantity fully covers requested quantity.
