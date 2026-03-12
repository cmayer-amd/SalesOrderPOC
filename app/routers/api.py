from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

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
