from __future__ import annotations

import math
from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.data_loader import DataStore
from app.reason_engine import (
    snapshot_sales_order,
    troubleshoot_orders,
)


router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="app/templates")
BASE_DIR = Path(__file__).resolve().parents[2]
DOCUMENT_FILES: dict[str, dict[str, str]] = {
    "readme": {"title": "README", "path": "README.md"},
    "functional-design": {"title": "Functional Design", "path": "FUNCTIONAL_DESIGN.md"},
    "scenario-test-plan": {"title": "Scenario Test Plan", "path": "SCENARIO_TEST_PLAN.md"},
    "management-one-pager": {"title": "POC Management One-Pager", "path": "POC_MANAGEMENT_ONE_PAGER.md"},
    "production-deployment-design": {
        "title": "Production Deployment Design",
        "path": "PRODUCTION_DEPLOYMENT_DESIGN.md",
    },
    "production-deployment-one-pager": {
        "title": "Production Deployment One-Pager",
        "path": "PRODUCTION_DEPLOYMENT_ONE_PAGER.md",
    },
}


def get_store() -> DataStore:
    from app.main import store

    return store


def get_snapshot_selection(snapshot_date: str | None) -> tuple[str, DataStore, list[str]]:
    from app.main import resolve_snapshot, snapshot_versions

    selected, snapshot_store = resolve_snapshot(snapshot_date)
    return selected, snapshot_store, snapshot_versions


def _fit_mail_cell(value: object, max_len: int) -> str:
    text = str(value or "")
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 3]}..."


def _mail_kv_line(label: str, value: object) -> str:
    return f"- {label}: {value}"


def _origin_context_from_params(params: dict[str, str]) -> tuple[list[str], dict[str, str], str]:
    src_map = {
        "src_sales_order": (params.get("src_sales_order") or "").strip(),
        "src_customer": (params.get("src_customer") or "").strip(),
        "src_material": (params.get("src_material") or "").strip(),
        "src_plant": (params.get("src_plant") or "").strip(),
        "src_snapshot_date": (params.get("src_snapshot_date") or "").strip(),
        "src_only_not_fully_on_request_date": (params.get("src_only_not_fully_on_request_date") or "").strip(),
        "src_page": (params.get("src_page") or "").strip(),
        "src_page_size": (params.get("src_page_size") or "").strip(),
    }
    compact = {k: v for k, v in src_map.items() if v}
    chips: list[str] = []
    if src_map["src_sales_order"]:
        chips.append(f"SO={src_map['src_sales_order']}")
    if src_map["src_customer"]:
        chips.append(f"Customer={src_map['src_customer']}")
    if src_map["src_material"]:
        chips.append(f"Part={src_map['src_material']}")
    if src_map["src_plant"]:
        chips.append(f"Plant={src_map['src_plant']}")
    if src_map["src_snapshot_date"]:
        chips.append(f"Snapshot={src_map['src_snapshot_date']}")
    if src_map["src_only_not_fully_on_request_date"] in {"1", "true", "yes", "on"}:
        chips.append("Readiness filter=ON")
    if src_map["src_page"] and src_map["src_page_size"]:
        chips.append(f"Page={src_map['src_page']} (size {src_map['src_page_size']})")
    suffix = f"&{urlencode(compact)}" if compact else ""
    return chips, compact, suffix


def _reason_label(code: str) -> str:
    normalized = str(code or "").strip()
    if not normalized:
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
        "PARTIAL_ALLOCATION_LIMIT": "Allocation Limited",
        "DELIVERED_GI_POSTED": "Delivered (GI Posted)",
        "DELIVERY_IN_PROCESS": "Delivery In Process",
        "DELIVERY_BLOCKED": "Delivery Blocked",
        "STOCK_AVAILABLE": "Stock Available",
        "PLANNED_ORDER_AVAILABLE": "Planned Order Available",
        "NO_SUPPLY_SOURCE_PLANT": "No Source Supply",
        "ALLOCATION_ACTIVE": "Allocation Active",
        "ALLOCATION_EXHAUSTED": "Allocation Exhausted",
        "PLANT_SUBSTITUTION_RULE": "Substitution Rule",
        "PLANT_SUBSTITUTION_APPLIED": "Substitution Applied",
        "PLANT_SUBSTITUTION_AVAILABLE": "Substitution Available",
        "SCHEDULE_PUSHED_OUT": "Pushed Out",
        "BOP_PARTIAL": "BOP Partial",
        "BOP_SUCCESS": "BOP Success",
        "NO_SCHEDULE_UNRESOLVED": "Unresolved",
    }
    if normalized in short_map:
        return short_map[normalized]
    return normalized.replace("_", " ").title()


def _decorate_result_labels(rows: list[dict[str, object]]) -> None:
    for row in rows:
        code = str(row.get("reason_code", "") or "")
        row["reason_label"] = _reason_label(code)
        contributing = row.get("contributing_reasons", [])
        normalized_contributing: list[dict[str, str]] = []
        if isinstance(contributing, list):
            for cr in contributing:
                if not isinstance(cr, dict):
                    continue
                c_code = str(cr.get("code", "") or "")
                normalized_contributing.append(
                    {
                        "code": c_code,
                        "label": _reason_label(c_code),
                        "text": str(cr.get("text", "") or ""),
                    }
                )
        row["contributing_labels"] = normalized_contributing


def _snapshot_review_mailto(report: dict[str, object]) -> str:
    sales_order = str(report.get("sales_order", ""))
    header = report.get("header", {}) if isinstance(report.get("header", {}), dict) else {}
    results = report.get("results", []) if isinstance(report.get("results", []), list) else []

    subject = f"Review Request: Sales Order {sales_order} Snapshot Analysis"
    schedule_count = len([r for r in results if isinstance(r, dict)])
    unscheduled_count = len(
        [
            r
            for r in results
            if isinstance(r, dict)
            and (
                (not str(r.get("schedule_date", "") or ""))
                or str(r.get("reason_code", "") or "").startswith("NO_SCHEDULE")
            )
        ]
    )
    delayed_count = len(
        [
            r
            for r in results
            if isinstance(r, dict)
            and str(r.get("schedule_date", "") or "")
            and str(r.get("requested_date", "") or "")
            and str(r.get("schedule_date", "") or "") > str(r.get("requested_date", "") or "")
        ]
    )

    summary_lines = [
        _mail_kv_line("Sales Order", _fit_mail_cell(sales_order, 24)),
        _mail_kv_line("Customer", _fit_mail_cell(header.get("customer", ""), 24)),
        _mail_kv_line("Region", _fit_mail_cell(header.get("region", ""), 24)),
        _mail_kv_line("Schedules", schedule_count),
        _mail_kv_line("Unscheduled", unscheduled_count),
        _mail_kv_line("Delayed", delayed_count),
    ]
    schedule_lines: list[str] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        reason_value = str(r.get("reason_label", "") or r.get("reason_code", "") or "")
        contributing = r.get("contributing_labels", r.get("contributing_reasons", []))
        contributing_codes = ", ".join(
            [
                str(c.get("label", "") or c.get("code", ""))
                for c in contributing
                if isinstance(c, dict) and (c.get("label", "") or c.get("code", ""))
            ]
        )
        schedule_lines.extend(
            [
                f"[{_fit_mail_cell(r.get('item_number', ''), 6)} / "
                f"{_fit_mail_cell(r.get('material', ''), 12)} / "
                f"Sch {_fit_mail_cell(r.get('schedule_line', ''), 6)}]",
                f"  Reason: {_fit_mail_cell(reason_value, 48)}",
                f"  Requested: Qty {_fit_mail_cell(r.get('requested_qty', ''), 10)} | "
                f"Date {_fit_mail_cell(r.get('requested_date', ''), 12)}",
                f"  Confirmed: Qty {_fit_mail_cell(r.get('confirmed_qty', ''), 10)} | "
                f"Date {_fit_mail_cell(r.get('schedule_date', ''), 12)}",
                f"  Contributing: {_fit_mail_cell(contributing_codes or 'None', 80)}",
                "",
            ]
        )

    lines = [
        "Hello Chris,",
        "",
        "Please review the snapshot schedule analysis below.",
        "",
        "ORDER SUMMARY",
        *summary_lines,
        "",
        "SCHEDULE DETAILS",
        *schedule_lines,
        "",
        "Regards,",
        "Sales Order Schedule Troubleshooter",
    ]
    body = "\n".join(lines)
    return f"mailto:cmayer@amd.com?subject={quote(subject)}&body={quote(body)}"


@router.get("/", response_class=HTMLResponse)
def index(request: Request, data_store: DataStore = Depends(get_store)) -> HTMLResponse:
    sales_order = (request.query_params.get("sales_order") or "").strip()
    customer = (request.query_params.get("customer") or "").strip()
    material = (request.query_params.get("material") or "").strip()
    plant = (request.query_params.get("plant") or "").strip()
    snapshot_date = (request.query_params.get("snapshot_date") or "").strip()
    only_not_fully_on_request_date = (
        (request.query_params.get("only_not_fully_on_request_date") or "").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    selected_snapshot_date, snapshot_store, available_snapshot_versions = get_snapshot_selection(snapshot_date)

    has_filters = any([sales_order, customer, material, plant, only_not_fully_on_request_date])
    page_raw = (request.query_params.get("page") or "1").strip()
    page_size_raw = (request.query_params.get("page_size") or "10").strip()
    try:
        page = max(int(page_raw), 1)
    except ValueError:
        page = 1
    try:
        page_size = int(page_size_raw)
    except ValueError:
        page_size = 10
    page_size = min(max(page_size, 1), 50)
    query_origin_params = {
        "src_sales_order": sales_order,
        "src_customer": customer,
        "src_material": material,
        "src_plant": plant,
        "src_snapshot_date": selected_snapshot_date,
        "src_only_not_fully_on_request_date": "1" if only_not_fully_on_request_date else "",
        "src_page": str(page),
        "src_page_size": str(page_size),
    }
    _, _, detail_link_suffix = _origin_context_from_params(query_origin_params)

    orders = snapshot_store.filter_sales_orders(
        sales_order=sales_order or None,
        customer=customer or None,
        material=material or None,
        plant=plant or None,
        only_not_fully_on_request_date=only_not_fully_on_request_date,
    )

    # When any query resolves to exactly one order, route to the same
    # detail UI users get from clicking the SO hyperlink.
    if len(orders) == 1:
        resolved_so = str(orders[0].get("sales_order", "") or "").strip()
        if resolved_so:
            return RedirectResponse(
                url=f"/orders/{resolved_so}?mode=snapshot&snapshot_date={selected_snapshot_date}{detail_link_suffix}",
                status_code=303,
            )

    query_report = None
    if has_filters:
        query_report = troubleshoot_orders(
            store=snapshot_store,
            sales_order=sales_order or None,
            customer=customer or None,
            material=material or None,
            plant=plant or None,
            only_not_fully_on_request_date=only_not_fully_on_request_date,
        )
        if isinstance(query_report, dict):
            _decorate_result_labels(query_report.get("results", []))
    row_class_map = snapshot_store.order_row_class_map()
    order_parts_map = snapshot_store.order_parts_map()
    for order in orders:
        so = order.get("sales_order", "")
        order["row_class"] = row_class_map.get(so, "")
        order["is_delayed"] = order["row_class"] == "row-delayed"
        order["is_unscheduled"] = order["row_class"] == "row-unscheduled"
        order["parts"] = order_parts_map.get(so, "")

    total_orders = len(orders)
    total_pages = math.ceil(total_orders / page_size) if total_orders > 0 else 0
    if total_pages > 0 and page > total_pages:
        page = total_pages
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paged_orders = orders[start_idx:end_idx]

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "orders": paged_orders,
            "dataset_counts": data_store.counts(),
            "query": {
                "sales_order": sales_order,
                "customer": customer,
                "material": material,
                "plant": plant,
                "snapshot_date": selected_snapshot_date,
                "snapshot_versions": available_snapshot_versions,
                "page_size": str(page_size),
                "only_not_fully_on_request_date": "1" if only_not_fully_on_request_date else "",
            },
            "has_filters": has_filters,
            "query_report": query_report,
            "detail_link_suffix": detail_link_suffix,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_orders": total_orders,
                "total_pages": total_pages,
                "has_prev": total_pages > 0 and page > 1,
                "prev_page": page - 1,
                "has_next": total_pages > 0 and page < total_pages,
                "next_page": page + 1,
                "page_size_options": [10, 25, 50],
            },
            "delayed_orders_count": len([v for v in row_class_map.values() if v == "row-delayed"]),
            "unscheduled_orders_count": len([v for v in row_class_map.values() if v == "row-unscheduled"]),
        },
    )


@router.get("/orders/{so_number}", response_class=HTMLResponse)
def order_detail(
    so_number: str,
    request: Request,
    data_store: DataStore = Depends(get_store),
) -> HTMLResponse:
    mode = "snapshot"
    snapshot_date = (request.query_params.get("snapshot_date") or "").strip()
    selected_snapshot_date, snapshot_store, available_snapshot_versions = get_snapshot_selection(snapshot_date)
    origin_context_chips, origin_hidden_fields, origin_query_suffix = _origin_context_from_params(
        {k: (request.query_params.get(k) or "") for k in request.query_params.keys()}
    )
    sidebar_rows: list[dict[str, str]] = []
    sidebar_label_map = [
        ("SO", "src_sales_order"),
        ("Cust", "src_customer"),
        ("Part", "src_material"),
        ("Plant", "src_plant"),
        ("Snapshot", "src_snapshot_date"),
        ("Page", "src_page"),
        ("Rows/Page", "src_page_size"),
    ]
    for label, key in sidebar_label_map:
        value = str(origin_hidden_fields.get(key, "") or "").strip()
        if value:
            sidebar_rows.append({"label": label, "value": value})
    readiness_raw = str(origin_hidden_fields.get("src_only_not_fully_on_request_date", "") or "").strip().lower()
    if readiness_raw in {"1", "true", "yes", "on"}:
        sidebar_rows.append({"label": "Readiness filter", "value": "Only orders not fully scheduled on requested date"})
    elif "src_only_not_fully_on_request_date" in origin_hidden_fields:
        sidebar_rows.append({"label": "Readiness filter", "value": "Off"})

    back_url = request.headers.get("referer", "/")
    bundle = snapshot_store.sales_order_bundle(so_number)
    if not bundle["header"]:
        return templates.TemplateResponse(
            request,
            "order_detail.html",
            {
                "error": f"Sales order {so_number} not found.",
                "report": None,
                "back_url": back_url,
                "snapshot_date": selected_snapshot_date,
                "snapshot_versions": available_snapshot_versions,
                "origin_context_chips": origin_context_chips,
                "origin_hidden_fields": origin_hidden_fields,
                "origin_query_suffix": origin_query_suffix,
                "origin_sidebar_rows": sidebar_rows,
            },
            status_code=404,
        )

    report = snapshot_sales_order(so_number, snapshot_store)
    if isinstance(report, dict):
        _decorate_result_labels(report.get("results", []))
    review_mailto = _snapshot_review_mailto(report)
    order_parts = sorted(
        {
            str(r.get("material", "") or "")
            for r in report.get("results", [])
            if isinstance(r, dict) and str(r.get("material", "") or "")
        }
    )

    return templates.TemplateResponse(
        request,
        "order_detail.html",
        {
            "error": None,
            "report": report,
            "mode": mode,
            "back_url": back_url,
            "review_mailto": review_mailto,
            "order_parts": order_parts,
            "snapshot_date": selected_snapshot_date,
            "snapshot_versions": available_snapshot_versions,
            "origin_context_chips": origin_context_chips,
            "origin_hidden_fields": origin_hidden_fields,
            "origin_query_suffix": origin_query_suffix,
            "origin_sidebar_rows": sidebar_rows,
        },
    )


@router.get("/datasets/{dataset_name}", response_class=HTMLResponse)
def dataset_view(
    dataset_name: str,
    request: Request,
    data_store: DataStore = Depends(get_store),
) -> HTMLResponse:
    if dataset_name not in data_store.dataset_keys():
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_name} not found.")

    preview = data_store.dataset_preview(dataset_name)
    return templates.TemplateResponse(
        request,
        "dataset_view.html",
        {
            "dataset_name": dataset_name,
            "dataset_file": data_store.dataset_filename(dataset_name),
            "columns": preview["columns"],
            "rows": preview["rows"],
            "row_count": preview["row_count"],
        },
    )


@router.get("/documents", response_class=HTMLResponse)
def documents_index(request: Request) -> HTMLResponse:
    docs = []
    for key, config in DOCUMENT_FILES.items():
        docs.append(
            {
                "key": key,
                "title": config["title"],
            }
        )

    return templates.TemplateResponse(
        request,
        "documents_index.html",
        {"documents": docs},
    )


@router.get("/documents/{doc_key}", response_class=HTMLResponse)
def document_view(doc_key: str, request: Request) -> HTMLResponse:
    config = DOCUMENT_FILES.get(doc_key)
    if not config:
        raise HTTPException(status_code=404, detail=f"Document {doc_key} not found.")

    file_path = BASE_DIR / config["path"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File {config['path']} not found.")

    content = file_path.read_text(encoding="utf-8", errors="replace")
    return templates.TemplateResponse(
        request,
        "document_view.html",
        {
            "doc_title": config["title"],
            "doc_content": content,
        },
    )
