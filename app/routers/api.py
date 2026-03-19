from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.data_loader import DataStore
from app.reason_engine import (
    determine_reason,
    snapshot_sales_order,
    troubleshoot_orders,
)


router = APIRouter(prefix="/api", tags=["api"])


def get_store() -> DataStore:
    from app.main import store

    return store


def get_snapshot_store(snapshot_date: str | None) -> DataStore:
    from app.main import resolve_snapshot

    _, snapshot_store = resolve_snapshot(snapshot_date)
    return snapshot_store


class ChatbotQueryRequest(BaseModel):
    message: str
    snapshot_date: str | None = None


def _reason_label(code: str) -> str:
    normalized = str(code or "").strip()
    if normalized == "":
        return ""
    short_map = {
        "CONFIRMED_FROM_STOCK": "Stock Confirmed",
        "PARTIAL_STOCK_PLANNED_ORDER": "Stock + Planned",
        "CONFIRMED_FROM_PLANNED_ORDER": "Planned Order Confirmed",
        "NO_SCHEDULE_ALLOCATION_EXHAUSTED": "Allocation Exhausted",
        "NO_SCHEDULE_NO_SUPPLY": "No Supply",
        "NO_SCHEDULE_MULTI_FACTOR": "Multi-Factor Block",
        "NO_SCHEDULE_DELIVERY_BLOCKED": "Delivery Blocked",
        "CONFIRMED_WITH_PLANT_SUBSTITUTION": "Substitution Confirmed",
        "NO_SCHEDULE_SUBSTITUTION_PENDING": "Substitution Pending",
        "SCHEDULE_PUSHED_OUT": "Pushed Out",
    }
    if normalized in short_map:
        return short_map[normalized]
    return normalized.replace("_", " ").title()


def _parse_chatbot_message(message: str) -> tuple[str | None, str | None]:
    text = str(message or "").strip()
    if text == "":
        return None, None

    lowered = text.lower()
    so_match = re.search(r"\b\d{8,12}\b", text)
    if so_match:
        return "sales_order", so_match.group(0)

    material_match = re.search(r"\b(?:part|material|mat)\b\s*[:=]?\s*([a-z0-9*?%_/-]+)", lowered)
    if material_match and material_match.group(1):
        return "material", material_match.group(1).upper()

    customer_match = re.search(r"\b(?:customer|cust)\b\s*[:=]?\s*([a-z0-9*?%_/-]+)", lowered)
    if customer_match and customer_match.group(1):
        return "customer", customer_match.group(1).upper()

    prefixed_so = re.search(
        r"\b(?:sales\s*order|order|so)\b\s*(?:number|num|id)?\s*[:=]?\s*([a-z0-9*?%_/-]*\d[a-z0-9*?%_/-]*)",
        lowered,
    )
    if prefixed_so and prefixed_so.group(1):
        return "sales_order", prefixed_so.group(1).upper()

    # Single-token fallback: numeric -> SO, otherwise part/material.
    if re.fullmatch(r"[0-9*?%_/-]{6,}", text):
        return "sales_order", text
    if re.fullmatch(r"[a-zA-Z0-9*?%_/-]+", text):
        return "material", text.upper()
    return None, None


@router.get("/health")
def health(data_store: DataStore = Depends(get_store)) -> dict[str, object]:
    return {"status": "ok", "dataset_counts": data_store.counts()}


@router.get("/sales-orders")
def list_sales_orders(
    sales_order: str | None = Query(default=None),
    customer: str | None = Query(default=None),
    material: str | None = Query(default=None),
    plant: str | None = Query(default=None),
    snapshot_date: str | None = Query(default=None),
    only_not_fully_on_request_date: bool = Query(default=False),
    data_store: DataStore = Depends(get_store),
) -> dict[str, object]:
    snapshot_store = get_snapshot_store(snapshot_date)
    orders = snapshot_store.filter_sales_orders(
        sales_order=sales_order,
        customer=customer,
        material=material,
        plant=plant,
        only_not_fully_on_request_date=only_not_fully_on_request_date,
    )
    return {"count": len(orders), "results": orders}


@router.get("/sales-orders/{so_number}")
def sales_order_detail(so_number: str, data_store: DataStore = Depends(get_store)) -> dict[str, object]:
    bundle = data_store.sales_order_bundle(so_number)
    if not bundle["header"]:
        raise HTTPException(status_code=404, detail="Sales order not found")
    return bundle


@router.get("/sales-orders/{so_number}/items/{item_number}")
def item_detail(
    so_number: str,
    item_number: str,
    data_store: DataStore = Depends(get_store),
) -> dict[str, object]:
    bundle = data_store.sales_order_bundle(so_number)
    if not bundle["header"]:
        raise HTTPException(status_code=404, detail="Sales order not found")

    item_rows = [r for r in bundle["items"] if r.get("item_number") == item_number]
    if not item_rows:
        raise HTTPException(status_code=404, detail="Item not found")

    schedules = [r for r in bundle["schedules"] if r.get("item_number") == item_number]
    return {"header": bundle["header"][0], "item": item_rows[0], "schedules": schedules}


@router.get("/sales-orders/{so_number}/items/{item_number}/schedules/{schedule_line}")
def schedule_detail(
    so_number: str,
    item_number: str,
    schedule_line: str,
    data_store: DataStore = Depends(get_store),
) -> dict[str, object]:
    bundle = data_store.sales_order_bundle(so_number)
    if not bundle["header"]:
        raise HTTPException(status_code=404, detail="Sales order not found")

    item_rows = [r for r in bundle["items"] if r.get("item_number") == item_number]
    schedule_rows = [
        r
        for r in bundle["schedules"]
        if r.get("item_number") == item_number and r.get("schedule_line") == schedule_line
    ]
    if not item_rows or not schedule_rows:
        raise HTTPException(status_code=404, detail="Schedule line not found")

    reason = determine_reason(bundle["header"][0], item_rows[0], schedule_rows[0], data_store)
    return reason


@router.get("/troubleshoot/{so_number}")
def troubleshoot(
    so_number: str,
    snapshot_date: str | None = Query(default=None),
    data_store: DataStore = Depends(get_store),
) -> dict[str, object]:
    snapshot_store = get_snapshot_store(snapshot_date)
    report = snapshot_sales_order(so_number, snapshot_store)

    if report.get("message") == "Sales order not found.":
        raise HTTPException(status_code=404, detail=report["message"])
    return report


@router.get("/troubleshoot")
def troubleshoot_query(
    sales_order: str | None = Query(default=None),
    customer: str | None = Query(default=None),
    material: str | None = Query(default=None),
    plant: str | None = Query(default=None),
    snapshot_date: str | None = Query(default=None),
    only_not_fully_on_request_date: bool = Query(default=False),
    data_store: DataStore = Depends(get_store),
) -> dict[str, object]:
    if not any([sales_order, customer, material, plant, only_not_fully_on_request_date]):
        raise HTTPException(
            status_code=400,
            detail=(
                "Provide at least one filter: sales_order, customer, material, plant, "
                "or only_not_fully_on_request_date=true."
            ),
        )

    snapshot_store = get_snapshot_store(snapshot_date)
    return troubleshoot_orders(
        store=snapshot_store,
        sales_order=sales_order,
        customer=customer,
        material=material,
        plant=plant,
        only_not_fully_on_request_date=only_not_fully_on_request_date,
    )


@router.post("/chatbot/query")
def chatbot_query(
    payload: ChatbotQueryRequest,
    data_store: DataStore = Depends(get_store),
) -> dict[str, object]:
    query_type, query_value = _parse_chatbot_message(payload.message)
    if not query_type or not query_value:
        return {
            "assistant_message": (
                "I can help with Sales Order, Customer, or Part queries. "
                "Try: 'order 5000000042', 'customer CUST-1001', or 'part MAT-006'."
            ),
            "query_type": None,
            "query_value": None,
            "count_orders": 0,
            "count_schedules": 0,
            "results": [],
        }

    snapshot_store = get_snapshot_store(payload.snapshot_date)
    filters = {
        "sales_order": query_value if query_type == "sales_order" else None,
        "customer": query_value if query_type == "customer" else None,
        "material": query_value if query_type == "material" else None,
        "plant": None,
    }
    report = troubleshoot_orders(store=snapshot_store, **filters)
    results = report.get("results", [])
    if not isinstance(results, list):
        results = []

    display_rows = []
    for row in results[:25]:
        if not isinstance(row, dict):
            continue
        display_rows.append(
            {
                "sales_order": row.get("sales_order", ""),
                "item_number": row.get("item_number", ""),
                "schedule_line": row.get("schedule_line", ""),
                "material": row.get("material", ""),
                "customer": row.get("customer", ""),
                "region": row.get("region", ""),
                "requested_date": row.get("requested_date", ""),
                "schedule_date": row.get("schedule_date", ""),
                "reason_code": row.get("reason_code", ""),
                "reason_label": _reason_label(str(row.get("reason_code", "") or "")),
                "reason_text": row.get("reason_text", ""),
                "contributing_reason_codes": [
                    str(c.get("code", "") or "")
                    for c in row.get("contributing_reasons", [])
                    if isinstance(c, dict) and str(c.get("code", "") or "")
                ],
                "contributing_reason_labels": [
                    _reason_label(str(c.get("code", "") or ""))
                    for c in row.get("contributing_reasons", [])
                    if isinstance(c, dict) and str(c.get("code", "") or "")
                ],
            }
        )

    count_orders = int(report.get("count_orders", 0) or 0)
    count_schedules = int(report.get("count_schedules", 0) or 0)
    if count_schedules == 0:
        assistant_message = (
            f"No matching schedules found for {query_type.replace('_', ' ')} '{query_value}'. "
            "Try wildcard search like '*', '?', '%' or '_'."
        )
    else:
        assistant_message = (
            f"Found {count_schedules} schedule lines across {count_orders} order(s) "
            f"for {query_type.replace('_', ' ')} '{query_value}'."
        )

    return {
        "assistant_message": assistant_message,
        "query_type": query_type,
        "query_value": query_value,
        "count_orders": count_orders,
        "count_schedules": count_schedules,
        "results": display_rows,
    }
