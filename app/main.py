from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.data_loader import DataStore
from app.routers.api import router as api_router
from app.routers.web import router as web_router


app = FastAPI(
    title="SAP Sales Order Schedule Date Troubleshooter",
    version="0.1.0",
    docs_url="/api-docs-internal",
    description=(
        "Starter FastAPI app for schedule-date reasoning using stock, allocation, "
        "deliveries, planned orders, and BOP logs."
    ),
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
store = DataStore.load(DATA_DIR)

# Snapshot date strategy:
# - latest: today
# - middle: 2 days before today
# - oldest: 3 days before middle (today - 5)
_snapshot_dates = [
    date.today(),
    date.today() - timedelta(days=2),
    date.today() - timedelta(days=5),
]
snapshot_versions = [d.isoformat() for d in _snapshot_dates]


def _build_snapshot_stores(base_store: DataStore) -> dict[str, DataStore]:
    if base_store.sales_orders.empty:
        return {snapshot_versions[0]: base_store, snapshot_versions[1]: base_store, snapshot_versions[2]: base_store}

    order_list = sorted(base_store.sales_orders["sales_order"].astype(str).tolist())
    latest_orders = set(order_list)
    mid_orders = set(order_list[5:]) if len(order_list) > 5 else set(order_list)
    oldest_orders = set(order_list[12:]) if len(order_list) > 12 else set(order_list)

    return {
        snapshot_versions[0]: base_store.subset_by_orders(latest_orders),
        snapshot_versions[1]: base_store.subset_by_orders(mid_orders),
        snapshot_versions[2]: base_store.subset_by_orders(oldest_orders),
    }


snapshot_stores = _build_snapshot_stores(store)


def resolve_snapshot(snapshot_date: str | None) -> tuple[str, DataStore]:
    selected = (snapshot_date or "").strip()
    if selected in snapshot_stores:
        return selected, snapshot_stores[selected]
    latest = snapshot_versions[0]
    return latest, snapshot_stores[latest]

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(web_router)
app.include_router(api_router)


@app.get("/docs", include_in_schema=False)
def docs_with_home_link() -> HTMLResponse:
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>API Docs</title>
  <style>
    body { margin: 0; font-family: "Segoe UI", Tahoma, sans-serif; background: #f4f6f8; }
    .topbar {
      display: flex; align-items: center; gap: 10px;
      padding: 10px 14px; border-bottom: 1px solid #d6dde5; background: #fff;
    }
    .topbar-right {
      margin-left: auto;
    }
    .home-link {
      display: inline-block; background: #0f2a44; color: #fff; text-decoration: none;
      border-radius: 6px; padding: 7px 12px; font-size: 13px; font-weight: 600;
    }
    .home-link:hover { background: #13365a; }
    .title { color: #17212f; font-weight: 600; }
    iframe { display: block; width: 100%; height: calc(100vh - 51px); border: 0; }
  </style>
</head>
<body>
  <div class="topbar">
    <span class="title">API Documentation</span>
    <div class="topbar-right">
      <a class="home-link" href="/">Home</a>
    </div>
  </div>
  <iframe src="/api-docs-internal" title="API Documentation"></iframe>
</body>
</html>
"""
    return HTMLResponse(content=html)
