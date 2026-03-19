from __future__ import annotations

from datetime import datetime
from typing import Any

from app.data_loader import DataStore


def _as_float(value: str | int | float | None) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def _can_fully_cover_requested_qty(current_row: dict[str, Any], snapshot_row: dict[str, Any]) -> bool:
    requested_qty = _as_float(snapshot_row.get("requested_qty"))
    current_confirmed_qty = _as_float(current_row.get("confirmed_qty"))
    if requested_qty <= 0:
        return current_confirmed_qty > 0
    return current_confirmed_qty >= requested_qty


def _project_current_schedule_date(current_row: dict[str, Any], snapshot_row: dict[str, Any]) -> str:
    """
    Derive a current-state schedule date for comparison.
    If current state can fully confirm quantity, assume request-date fulfillment.
    """
    current_reason_code = str(current_row.get("reason_code", "") or "")
    if current_reason_code.startswith("NO_SCHEDULE"):
        return ""

    requested_date = str(snapshot_row.get("requested_date", "") or "")
    raw_current_schedule_date = str(current_row.get("schedule_date", "") or "")

    if requested_date and _can_fully_cover_requested_qty(current_row, snapshot_row):
        return requested_date
    if raw_current_schedule_date:
        return raw_current_schedule_date
    return requested_date


def _is_pushed_out(schedule: dict[str, Any]) -> bool:
    requested_date = str(schedule.get("requested_date", "") or "")
    schedule_date = str(schedule.get("schedule_date", "") or "")
    return bool(requested_date and schedule_date and schedule_date > requested_date)


def _earliest_row_date(rows: list[dict[str, Any]], field_name: str) -> str:
    dates = [str(r.get(field_name, "") or "") for r in rows if str(r.get(field_name, "") or "")]
    return min(dates) if dates else ""


def _pushed_out_explanation(
    requested_date: str,
    schedule_date: str,
    stock_qty: float,
    planned_qty: float,
    earliest_stock_date: str,
    earliest_planned_date: str,
    reason_code: str = "",
) -> str:
    if not requested_date or not schedule_date or schedule_date <= requested_date:
        return ""

    prefix = (
        f"Requested date ({requested_date}) is earlier than recorded schedule date ({schedule_date})."
    )

    has_stock = stock_qty > 0
    has_planned = planned_qty > 0

    if reason_code == "CONFIRMED_FROM_STOCK" and has_stock:
        if earliest_stock_date and earliest_stock_date > requested_date:
            return f"{prefix} Stock availability date ({earliest_stock_date}) is after the requested date."
        return (
            f"{prefix} Stock is available, but scheduling/sequence constraints delayed confirmation beyond the requested date."
        )

    if reason_code == "CONFIRMED_FROM_PLANNED_ORDER" and has_planned:
        if earliest_planned_date and earliest_planned_date > requested_date:
            return (
                f"{prefix} Planned-order supply is available on {earliest_planned_date}, which is after the requested date."
            )
        return f"{prefix} Confirmation depends on planned-order timing after the requested date."

    if reason_code == "PARTIAL_STOCK_PLANNED_ORDER" and has_stock and has_planned:
        if earliest_planned_date and earliest_planned_date > requested_date:
            return (
                f"{prefix} Source stock contributes, but full requested quantity also depends on planned-order "
                f"supply available on {earliest_planned_date}."
            )
        return (
            f"{prefix} Partial stock exists, and remaining quantity is covered by later supply timing constraints."
        )

    if has_stock and has_planned:
        if earliest_stock_date and earliest_stock_date <= requested_date and earliest_planned_date and earliest_planned_date > requested_date:
            return (
                f"{prefix} Source stock exists by requested date, but full requested quantity also depends on "
                f"planned-order supply available on {earliest_planned_date}."
            )
        if earliest_stock_date and earliest_stock_date > requested_date:
            return f"{prefix} Stock becomes available on {earliest_stock_date}, after the requested date."
        if earliest_planned_date and earliest_planned_date > requested_date:
            return f"{prefix} Planned-order supply date ({earliest_planned_date}) is after the requested date."
        return (
            f"{prefix} Stock and planned orders exist, but not enough supply is available on the requested date "
            "to confirm the schedule on time."
        )

    if has_stock:
        if earliest_stock_date and earliest_stock_date > requested_date:
            return f"{prefix} Stock availability date ({earliest_stock_date}) is after the requested date."
        return (
            f"{prefix} Stock exists, but available quantity/timing at request date is insufficient for full on-time confirmation."
        )

    if has_planned:
        if earliest_planned_date and earliest_planned_date > requested_date:
            return (
                f"{prefix} Planned-order supply is available on {earliest_planned_date}, which is after the requested date."
            )
        return f"{prefix} Confirmation depends on planned-order supply timing after the requested date."

    return f"{prefix} No usable supply is available by the requested date."


def _allocation_candidates(item: dict[str, Any], header: dict[str, Any], store: DataStore) -> list[dict[str, Any]]:
    if store.allocations.empty:
        return []

    df = store.allocations.copy()
    df = df[(df["material"] == item.get("material", "")) & (df["plant"] == item.get("plant", ""))]

    customer = header.get("customer", "")
    region = header.get("region", "")
    sold_to = header.get("sold_to", "")
    ship_to = header.get("ship_to", "")

    level3 = df[
        (df["allocation_level"] == "CUSTOMER_SOLDTO_SHIPTO")
        & (df["customer"] == customer)
        & (df["sold_to"] == sold_to)
        & (df["ship_to"] == ship_to)
    ]
    level2 = df[
        (df["allocation_level"] == "CUSTOMER_REGION")
        & (df["customer"] == customer)
        & (df["region"] == region)
    ]
    level1 = df[(df["allocation_level"] == "CUSTOMER") & (df["customer"] == customer)]

    for frame in (level3, level2, level1):
        if not frame.empty:
            return frame.to_dict(orient="records")
    return []


def _supply_rows_for_scope(
    store: DataStore,
    material: str,
    plant: str,
    storage_location: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float, float]:
    stock_rows: list[dict[str, Any]] = []
    planned_rows: list[dict[str, Any]] = []
    stock_qty = 0.0
    planned_qty = 0.0

    if not store.stock_supply.empty:
        stock_df = store.stock_supply[
            (store.stock_supply["material"] == material)
            & (store.stock_supply["plant"] == plant)
            & (store.stock_supply["storage_location"] == storage_location)
        ]
        stock_rows = stock_df.to_dict(orient="records")
        stock_qty = sum(_as_float(r.get("available_qty")) for r in stock_rows)

    if not store.planned_orders.empty:
        planned_df = store.planned_orders[
            (store.planned_orders["material"] == material)
            & (store.planned_orders["plant"] == plant)
            & (store.planned_orders["storage_location"] == storage_location)
        ]
        planned_rows = planned_df.to_dict(orient="records")
        planned_qty = sum(_as_float(r.get("planned_qty")) for r in planned_rows)

    return stock_rows, planned_rows, stock_qty, planned_qty


def _substitution_evidence(item: dict[str, Any], store: DataStore) -> tuple[list[dict[str, Any]], float]:
    """Return substitution evidence rows and total alternate-plant coverage qty."""
    if store.plant_substitutions.empty:
        return [], 0.0

    rules_df = store.plant_substitutions[
        (store.plant_substitutions["material"] == item.get("material", ""))
        & (store.plant_substitutions["source_plant"] == item.get("plant", ""))
    ]
    if rules_df.empty:
        return [], 0.0

    evidence: list[dict[str, Any]] = []
    total_coverage = 0.0
    for rule in rules_df.to_dict(orient="records"):
        target_plant = rule.get("target_plant", "")
        target_sloc = rule.get("target_storage_location", "")
        target_stock_rows, target_planned_rows, target_stock_qty, target_planned_qty = _supply_rows_for_scope(
            store=store,
            material=item.get("material", ""),
            plant=target_plant,
            storage_location=target_sloc,
        )
        coverage_qty = target_stock_qty + target_planned_qty
        if coverage_qty <= 0:
            continue
        total_coverage += coverage_qty
        evidence.append(
            {
                "rule": rule,
                "target_stock_rows": target_stock_rows,
                "target_planned_rows": target_planned_rows,
                "target_coverage_qty": coverage_qty,
            }
        )

    return evidence, total_coverage


def _successful_supply_reason(
    req_qty: float,
    conf_qty: float,
    schedule_date: str,
    schedule_status: str,
    stock_qty: float,
    planned_qty: float,
    substitution_coverage: float,
    alloc_remaining: float,
    is_delivery_blocked: bool,
) -> tuple[str, str] | None:
    """
    Determine if the line should be treated as successfully scheduled.
    A line is successful when requested quantity is fully confirmed, no hard
    blockers exist, and stock/planned/substitution coverage can satisfy demand.
    """
    if req_qty <= 0 or conf_qty < req_qty:
        return None
    # Do not classify as successful unless schedule line is actually confirmed.
    if not schedule_date or str(schedule_status or "").upper() == "UNCONFIRMED":
        return None
    if is_delivery_blocked or alloc_remaining <= 0:
        return None

    source_supply = stock_qty + planned_qty
    effective_supply = source_supply + substitution_coverage
    if effective_supply < req_qty:
        return None

    if stock_qty >= req_qty:
        return "CONFIRMED_FROM_STOCK", "Stock fully covers requested quantity."
    if source_supply >= req_qty:
        if stock_qty > 0:
            return "PARTIAL_STOCK_PLANNED_ORDER", "Partial stock plus planned orders provide coverage."
        return "CONFIRMED_FROM_PLANNED_ORDER", "Planned orders provide required supply."
    if substitution_coverage > 0:
        return (
            "CONFIRMED_WITH_PLANT_SUBSTITUTION",
            "Source supply is insufficient; substitute-plant supply closes the gap.",
        )
    return None


def determine_reason(
    header: dict[str, Any],
    item: dict[str, Any],
    schedule: dict[str, Any],
    store: DataStore,
) -> dict[str, Any]:
    so = schedule.get("sales_order", "")
    item_no = schedule.get("item_number", "")
    sched_no = schedule.get("schedule_line", "")
    req_qty = _as_float(schedule.get("requested_qty"))
    conf_qty = _as_float(schedule.get("confirmed_qty"))
    schedule_date = str(schedule.get("schedule_date", "") or "")
    schedule_status = str(schedule.get("schedule_status", "") or "")

    contributing: list[dict[str, str]] = []
    deliveries = []
    if not store.deliveries.empty:
        deliveries = store.deliveries[
            (store.deliveries["sales_order"] == so) & (store.deliveries["item_number"] == item_no)
        ].to_dict(orient="records")
    is_delivery_posted = False
    is_delivery_in_process = False
    is_delivery_blocked = False
    for delivery in deliveries:
        gi_status = delivery.get("gi_status", "")
        if gi_status == "POSTED":
            is_delivery_posted = True
        if gi_status in {"PARTIAL", "NOT_STARTED"}:
            is_delivery_in_process = True
        if delivery.get("delivery_block", "").upper() == "Y":
            is_delivery_blocked = True

    if is_delivery_posted:
        contributing.append({"code": "DELIVERED_GI_POSTED", "text": "Delivery exists and GI is posted."})
    elif is_delivery_blocked:
        contributing.append({"code": "DELIVERY_BLOCKED", "text": "Delivery block is active and prevents release."})
    elif is_delivery_in_process:
        contributing.append({"code": "DELIVERY_IN_PROCESS", "text": "Delivery document exists and is in process."})

    stock_rows, planned_rows, stock_qty, planned_qty = _supply_rows_for_scope(
        store=store,
        material=item.get("material", ""),
        plant=item.get("plant", ""),
        storage_location=item.get("storage_location", ""),
    )
    no_source_supply = stock_qty + planned_qty <= 0
    if stock_qty > 0:
        contributing.append({"code": "STOCK_AVAILABLE", "text": "Stock is available at the requested source plant."})
    if planned_qty > 0:
        contributing.append({"code": "PLANNED_ORDER_AVAILABLE", "text": "Planned orders contribute supply for this scope."})
    if no_source_supply:
        contributing.append({"code": "NO_SUPPLY_SOURCE_PLANT", "text": "No stock or planned order supply at source plant."})

    alloc_rows = _allocation_candidates(item, header, store)
    alloc_remaining = max((_as_float(r.get("remaining_qty")) for r in alloc_rows), default=req_qty)
    if alloc_rows and alloc_remaining <= 0:
        contributing.append({"code": "ALLOCATION_EXHAUSTED", "text": "Allocation exists but remaining quota is exhausted."})
    elif alloc_rows:
        contributing.append({"code": "ALLOCATION_ACTIVE", "text": "Allocation constraint matched for this request."})

    substitution_rows, substitution_coverage = _substitution_evidence(item=item, store=store)
    if substitution_rows and substitution_coverage > 0:
        contributing.append(
            {
                "code": "PLANT_SUBSTITUTION_RULE",
                "text": "Plant substitution rule exists and alternate-plant supply is available.",
            }
        )

    bop_rows = []
    if not store.bop_logs.empty:
        bop_rows = store.bop_logs[
            (store.bop_logs["sales_order"] == so)
            & (store.bop_logs["item_number"] == item_no)
            & (store.bop_logs["schedule_line"] == sched_no)
        ].to_dict(orient="records")

    reason_code = "NO_SCHEDULE_UNRESOLVED"
    reason_text = "No deterministic reason matched all conditions."

    source_supply = stock_qty + planned_qty
    effective_supply = source_supply + substitution_coverage
    is_pushed_out = _is_pushed_out(schedule)
    earliest_stock_date = _earliest_row_date(stock_rows, "stock_date")
    earliest_planned_date = _earliest_row_date(planned_rows, "available_date")

    line_is_confirmed = bool(schedule_date) and schedule_status.upper() != "UNCONFIRMED" and conf_qty > 0

    if is_delivery_blocked and no_source_supply:
        reason_code = "NO_SCHEDULE_MULTI_FACTOR"
        reason_text = "Multiple blockers: active delivery block and no source-plant supply."
    elif is_delivery_blocked:
        reason_code = "NO_SCHEDULE_DELIVERY_BLOCKED"
        reason_text = "Delivery block is active and prevents scheduling."
    elif is_delivery_posted:
        reason_code = "DELIVERED_GI_POSTED"
        reason_text = "Delivery exists and GI is posted."
    elif line_is_confirmed and req_qty > 0 and stock_qty >= req_qty and alloc_remaining >= req_qty:
        reason_code = "CONFIRMED_FROM_STOCK"
        reason_text = "Stock fully covers requested quantity."
    elif line_is_confirmed and req_qty > 0 and source_supply < req_qty and effective_supply >= req_qty and alloc_remaining > 0:
        reason_code = "CONFIRMED_WITH_PLANT_SUBSTITUTION"
        if no_source_supply:
            reason_text = "Source plant has no supply; schedule is supported by plant substitution supply."
        else:
            reason_text = "Source supply is insufficient; substitute-plant supply closes the gap."
        contributing.append({"code": "PLANT_SUBSTITUTION_APPLIED", "text": "Alternate-plant substitution supply is applied."})
    elif line_is_confirmed and req_qty > 0 and source_supply >= req_qty:
        if alloc_remaining <= 0:
            reason_code = "NO_SCHEDULE_ALLOCATION_EXHAUSTED"
            reason_text = "Supply exists but allocation remaining quantity is exhausted."
        elif stock_qty > 0:
            reason_code = "PARTIAL_STOCK_PLANNED_ORDER"
            reason_text = "Partial stock plus planned orders provide coverage."
        else:
            reason_code = "CONFIRMED_FROM_PLANNED_ORDER"
            reason_text = "Planned orders provide required supply."
    elif alloc_rows and alloc_remaining <= 0:
        reason_code = "NO_SCHEDULE_ALLOCATION_EXHAUSTED"
        reason_text = "Allocation hierarchy matched but no remaining quota is available."
    elif conf_qty > 0 and conf_qty < req_qty:
        reason_code = "PARTIAL_ALLOCATION_LIMIT"
        reason_text = "Confirmation is partial due to allocation cap or constrained supply."
    elif no_source_supply and substitution_coverage <= 0:
        reason_code = "NO_SCHEDULE_NO_SUPPLY"
        reason_text = "No stock and no planned order supply found for requested scope."
    elif not line_is_confirmed and source_supply >= req_qty and alloc_remaining > 0 and not is_delivery_blocked:
        reason_code = "NO_SCHEDULE_UNRESOLVED"
        reason_text = (
            "Stock/planned supply exists, but this line is not confirmed yet "
            "(no confirmed schedule date/quantity in the current dataset row)."
        )
    elif no_source_supply and substitution_coverage > 0:
        reason_code = "NO_SCHEDULE_SUBSTITUTION_PENDING"
        reason_text = "Substitution rule exists, but substitution supply was not applied."
        contributing.append({"code": "PLANT_SUBSTITUTION_AVAILABLE", "text": "Alternate-plant supply exists via substitution rule."})
    elif is_delivery_in_process:
        reason_code = "DELIVERY_IN_PROCESS"
        reason_text = "Delivery document exists and is in process."

    # Guardrail: when supply can satisfy and the line is fully confirmed with no
    # hard blockers, force a successful scheduled outcome.
    success_override = _successful_supply_reason(
        req_qty=req_qty,
        conf_qty=conf_qty,
        schedule_date=schedule_date,
        schedule_status=schedule_status,
        stock_qty=stock_qty,
        planned_qty=planned_qty,
        substitution_coverage=substitution_coverage,
        alloc_remaining=alloc_remaining,
        is_delivery_blocked=is_delivery_blocked,
    )
    if success_override and reason_code in {
        "NO_SCHEDULE_UNRESOLVED",
        "NO_SCHEDULE_NO_SUPPLY",
        "NO_SCHEDULE_SUBSTITUTION_PENDING",
        "PARTIAL_ALLOCATION_LIMIT",
    }:
        reason_code, reason_text = success_override

    if is_pushed_out and (
        reason_code in {"CONFIRMED_FROM_STOCK", "PARTIAL_STOCK_PLANNED_ORDER", "CONFIRMED_FROM_PLANNED_ORDER"}
        or any(
            r.get("code") in {"STOCK_AVAILABLE", "PLANNED_ORDER_AVAILABLE"}
            for r in contributing
        )
    ):
        pushout_text = _pushed_out_explanation(
            requested_date=str(schedule.get("requested_date", "") or ""),
            schedule_date=str(schedule.get("schedule_date", "") or ""),
            stock_qty=stock_qty,
            planned_qty=planned_qty,
            earliest_stock_date=earliest_stock_date,
            earliest_planned_date=earliest_planned_date,
            reason_code=reason_code,
        )
        reason_text = f"{reason_text} {pushout_text}"
        contributing.append({"code": "SCHEDULE_PUSHED_OUT", "text": pushout_text})

    return _result(
        item=item,
        reason_code=reason_code,
        reason_text=reason_text,
        schedule=schedule,
        stock_rows=stock_rows,
        alloc_rows=alloc_rows,
        delivery_rows=deliveries,
        planned_rows=planned_rows,
        bop_rows=bop_rows,
        contributing_reasons=_normalize_contributing_reasons(contributing),
        substitution_rows=substitution_rows,
    )


def _result(
    item: dict[str, Any],
    reason_code: str,
    reason_text: str,
    schedule: dict[str, Any],
    stock_rows: list[dict[str, Any]],
    alloc_rows: list[dict[str, Any]],
    delivery_rows: list[dict[str, Any]],
    planned_rows: list[dict[str, Any]],
    bop_rows: list[dict[str, Any]],
    contributing_reasons: list[dict[str, str]],
    substitution_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "scope": "SCHEDULE",
        "sales_order": schedule.get("sales_order", ""),
        "item_number": schedule.get("item_number", ""),
        "schedule_line": schedule.get("schedule_line", ""),
        "material": item.get("material", ""),
        "plant": item.get("plant", ""),
        "reason_code": reason_code,
        "reason_text": reason_text,
        "requested_qty": schedule.get("requested_qty", ""),
        "confirmed_qty": schedule.get("confirmed_qty", ""),
        "requested_date": schedule.get("requested_date", ""),
        "schedule_date": schedule.get("schedule_date", ""),
        "contributing_reasons": contributing_reasons,
        "evidence": {
            "stock": stock_rows,
            "allocation": alloc_rows,
            "deliveries": delivery_rows,
            "planned_orders": planned_rows,
            "bop_logs": bop_rows,
            "plant_substitutions": substitution_rows,
        },
    }


def troubleshoot_sales_order(so_number: str, store: DataStore) -> dict[str, Any]:
    bundle = store.sales_order_bundle(so_number)
    if not bundle["header"]:
        return {"sales_order": so_number, "items": [], "message": "Sales order not found."}

    return _troubleshoot_bundle(bundle, store)


def troubleshoot_orders(
    store: DataStore,
    sales_order: str | None = None,
    customer: str | None = None,
    material: str | None = None,
    plant: str | None = None,
    only_not_fully_on_request_date: bool = False,
) -> dict[str, Any]:
    """Analyze schedule reasons for all orders matching the provided filters."""
    matched_orders = store.filter_sales_orders(
        sales_order=sales_order,
        customer=customer,
        material=material,
        plant=plant,
        only_not_fully_on_request_date=only_not_fully_on_request_date,
    )

    filters = {
        "sales_order": sales_order or "",
        "customer": customer or "",
        "material": material or "",
        "plant": plant or "",
        "only_not_fully_on_request_date": only_not_fully_on_request_date,
    }

    if not matched_orders:
        return {
            "filters": filters,
            "count_orders": 0,
            "count_schedules": 0,
            "orders": [],
            "results": [],
        }

    order_results: list[dict[str, Any]] = []
    all_results: list[dict[str, Any]] = []
    for order in matched_orders:
        so_number = order.get("sales_order", "")
        bundle = store.sales_order_bundle(so_number)
        if not bundle["header"]:
            continue
        report = _troubleshoot_bundle(bundle, store)
        order_results.append(report)
        all_results.extend(report["results"])

    return {
        "filters": filters,
        "count_orders": len(order_results),
        "count_schedules": len(all_results),
        "orders": order_results,
        "results": all_results,
    }


def _troubleshoot_bundle(bundle: dict[str, Any], store: DataStore) -> dict[str, Any]:
    header = bundle["header"][0]
    item_index = {
        (row.get("sales_order", ""), row.get("item_number", "")): row for row in bundle["items"]
    }

    analyzed = []
    for schedule in bundle["schedules"]:
        key = (schedule.get("sales_order", ""), schedule.get("item_number", ""))
        item = item_index.get(key, {})
        result = determine_reason(header, item, schedule, store)
        result["customer"] = header.get("customer", "")
        result["region"] = header.get("region", "")
        analyzed.append(result)

    return {"sales_order": header.get("sales_order", ""), "header": header, "results": analyzed}


def _snapshot_reason_from_schedule(schedule: dict[str, Any]) -> tuple[str, str]:
    reason_code = schedule.get("reason_code_expected", "") or ""
    if reason_code:
        # BOP failure is no longer a valid business outcome.
        if reason_code == "NO_SCHEDULE_BOP_FAILED":
            return "NO_SCHEDULE_NO_SUPPLY", "Recorded run indicates no feasible supply."
        return reason_code, "Recorded reason captured from last run dataset."

    atp = schedule.get("atp_check_result", "")
    if atp == "ATP_OK":
        return "CONFIRMED_FROM_STOCK", "Recorded ATP check indicates confirmed state."
    if atp in {"ATP_DELAY", "ATP_PLANNED_ORDER"}:
        if _is_pushed_out(schedule):
            return (
                "PARTIAL_STOCK_PLANNED_ORDER",
                "Recorded ATP indicates delayed/planned confirmation with schedule pushed beyond requested date.",
            )
        return "PARTIAL_STOCK_PLANNED_ORDER", "Recorded ATP indicates delayed/planned confirmation."
    if atp == "ATP_NO_SUPPLY":
        return "NO_SCHEDULE_NO_SUPPLY", "Recorded ATP indicates no supply."
    if atp == "ATP_BOP_FAIL":
        return "NO_SCHEDULE_NO_SUPPLY", "Recorded ATP indicates no feasible supply."
    return "NO_SCHEDULE_UNRESOLVED", "Recorded reason is not explicitly captured."


def _snapshot_contributing_reasons(
    schedule: dict[str, Any],
    last_bop: dict[str, Any],
    deliveries: list[dict[str, Any]],
    pushed_out_text: str = "",
) -> list[dict[str, str]]:
    reasons: list[dict[str, str]] = []
    atp = schedule.get("atp_check_result", "")

    # Delivery-state contributors from recorded delivery rows.
    for d in deliveries:
        gi = d.get("gi_status", "")
        if gi == "POSTED":
            reasons.append({"code": "DELIVERED_GI_POSTED", "text": "Recorded delivery has GI posted."})
            break
    for d in deliveries:
        gi = d.get("gi_status", "")
        if gi in {"PARTIAL", "NOT_STARTED"}:
            reasons.append({"code": "DELIVERY_IN_PROCESS", "text": "Recorded delivery is in process."})
            break
    for d in deliveries:
        if d.get("delivery_block", "").upper() == "Y":
            reasons.append({"code": "DELIVERY_BLOCKED", "text": "Recorded delivery block was active at run time."})
            break

    # ATP-coded contributors from recorded schedule status.
    mapping: dict[str, list[dict[str, str]]] = {
        "ATP_OK": [{"code": "STOCK_AVAILABLE", "text": "Recorded supply confirmed from available stock."}],
        "ATP_DELAY": [
            {"code": "STOCK_AVAILABLE", "text": "Recorded run had partial source stock."},
            {"code": "PLANNED_ORDER_AVAILABLE", "text": "Recorded run used planned-order coverage."},
        ],
        "ATP_PLANNED_ORDER": [
            {"code": "PLANNED_ORDER_AVAILABLE", "text": "Recorded run depended on planned-order coverage."}
        ],
        "ATP_ALLOC_LIMIT": [{"code": "ALLOCATION_ACTIVE", "text": "Recorded run was constrained by allocation rules."}],
        "ATP_ALLOC_EXHAUSTED": [{"code": "ALLOCATION_EXHAUSTED", "text": "Recorded allocation was exhausted."}],
        "ATP_NO_SUPPLY": [{"code": "NO_SUPPLY_SOURCE_PLANT", "text": "Recorded run found no source-plant supply."}],
        "ATP_NO_SUPPLY_BLOCKED": [
            {"code": "NO_SUPPLY_SOURCE_PLANT", "text": "Recorded run found no source-plant supply."},
            {"code": "DELIVERY_BLOCKED", "text": "Recorded run had delivery block impact."},
        ],
        "ATP_BOP_FAIL": [{"code": "NO_SUPPLY_SOURCE_PLANT", "text": "Recorded ATP indicates no feasible supply."}],
        "ATP_SUBSTITUTION": [{"code": "PLANT_SUBSTITUTION_RULE", "text": "Recorded run used plant substitution logic."}],
    }
    reasons.extend(mapping.get(atp, []))

    if _is_pushed_out(schedule):
        reasons.append(
            {
                "code": "SCHEDULE_PUSHED_OUT",
                "text": (
                    pushed_out_text
                    or (
                        "Recorded schedule date is later than requested date, indicating supply timing "
                        "or scheduling constraints."
                    )
                ),
            }
        )

    # Last BOP context contributor.
    bop_status = last_bop.get("bop_status", "")
    if bop_status == "PARTIAL":
        reasons.append({"code": "BOP_PARTIAL", "text": "Last recorded BOP entry was partial."})
    elif bop_status == "SUCCESS":
        reasons.append({"code": "BOP_SUCCESS", "text": "Last recorded BOP entry succeeded."})

    return _normalize_contributing_reasons(reasons)


def _fallback_contributing_reason(reason_code: str, reason_text: str) -> list[dict[str, str]]:
    if not reason_code:
        return []
    return [{"code": reason_code, "text": reason_text or "Recorded/derived primary reason."}]


def _normalize_contributing_reasons(reasons: list[dict[str, str]]) -> list[dict[str, str]]:
    """Deduplicate and remove mutually-exclusive delivery conflicts."""
    if not reasons:
        return []

    # Keep at most one delivery-state reason.
    delivery_precedence = ["DELIVERED_GI_POSTED", "DELIVERY_BLOCKED", "DELIVERY_IN_PROCESS"]
    selected_delivery_code = ""
    for code in delivery_precedence:
        if any(r.get("code") == code for r in reasons):
            selected_delivery_code = code
            break

    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for r in reasons:
        code = r.get("code", "")
        if not code:
            continue
        if code in {"DELIVERED_GI_POSTED", "DELIVERY_BLOCKED", "DELIVERY_IN_PROCESS"}:
            if code != selected_delivery_code:
                continue
        if code in seen:
            continue
        normalized.append(r)
        seen.add(code)
    return normalized


def _last_bop_entry(
    store: DataStore,
    sales_order: str,
    item_number: str,
    schedule_line: str,
) -> dict[str, Any]:
    if store.bop_logs.empty:
        return {}

    rows = store.bop_logs[
        (store.bop_logs["sales_order"] == sales_order)
        & (store.bop_logs["item_number"] == item_number)
        & (store.bop_logs["schedule_line"] == schedule_line)
    ].to_dict(orient="records")
    if not rows:
        return {}

    rows.sort(key=lambda r: r.get("log_timestamp", ""))
    return rows[-1]


def snapshot_sales_order(so_number: str, store: DataStore) -> dict[str, Any]:
    """Return status based on snapshot data from last run / last BOP context."""
    bundle = store.sales_order_bundle(so_number)
    if not bundle["header"]:
        return {"sales_order": so_number, "items": [], "message": "Sales order not found."}

    header = bundle["header"][0]
    item_index = {(r.get("sales_order", ""), r.get("item_number", "")): r for r in bundle["items"]}
    results: list[dict[str, Any]] = []

    for schedule in bundle["schedules"]:
        so = schedule.get("sales_order", "")
        item_no = schedule.get("item_number", "")
        sched_no = schedule.get("schedule_line", "")
        item = item_index.get((so, item_no), {})

        last_bop = _last_bop_entry(store, so, item_no, sched_no)
        deliveries = []
        if not store.deliveries.empty:
            deliveries = store.deliveries[
                (store.deliveries["sales_order"] == so) & (store.deliveries["item_number"] == item_no)
            ].to_dict(orient="records")
        reason_code, reason_text = _snapshot_reason_from_schedule(schedule)
        stock_rows, planned_rows, stock_qty, planned_qty = _supply_rows_for_scope(
            store=store,
            material=item.get("material", ""),
            plant=item.get("plant", ""),
            storage_location=item.get("storage_location", ""),
        )
        req_qty = _as_float(schedule.get("requested_qty"))
        conf_qty = _as_float(schedule.get("confirmed_qty"))
        schedule_date = str(schedule.get("schedule_date", "") or "")
        schedule_status = str(schedule.get("schedule_status", "") or "")
        alloc_rows = _allocation_candidates(item, header, store)
        alloc_remaining = max((_as_float(r.get("remaining_qty")) for r in alloc_rows), default=req_qty)
        is_delivery_blocked = any(d.get("delivery_block", "").upper() == "Y" for d in deliveries)
        substitution_rows, substitution_coverage = _substitution_evidence(item=item, store=store)
        success_override = _successful_supply_reason(
            req_qty=req_qty,
            conf_qty=conf_qty,
            schedule_date=schedule_date,
            schedule_status=schedule_status,
            stock_qty=stock_qty,
            planned_qty=planned_qty,
            substitution_coverage=substitution_coverage,
            alloc_remaining=alloc_remaining,
            is_delivery_blocked=is_delivery_blocked,
        )
        if success_override and reason_code.startswith("NO_SCHEDULE"):
            reason_code, reason_text = success_override
        pushed_out_text = _pushed_out_explanation(
            requested_date=str(schedule.get("requested_date", "") or ""),
            schedule_date=str(schedule.get("schedule_date", "") or ""),
            stock_qty=stock_qty,
            planned_qty=planned_qty,
            earliest_stock_date=_earliest_row_date(stock_rows, "stock_date"),
            earliest_planned_date=_earliest_row_date(planned_rows, "available_date"),
            reason_code=reason_code,
        )
        if pushed_out_text:
            reason_text = f"{reason_text} {pushed_out_text}"
        contributing_reasons = _snapshot_contributing_reasons(
            schedule=schedule,
            last_bop=last_bop,
            deliveries=deliveries,
            pushed_out_text=pushed_out_text,
        )
        if not contributing_reasons:
            contributing_reasons = _fallback_contributing_reason(reason_code, reason_text)
        contributing_reasons = _normalize_contributing_reasons(contributing_reasons)
        results.append(
            {
                "scope": "SCHEDULE",
                "sales_order": so,
                "item_number": item_no,
                "schedule_line": sched_no,
                "material": item.get("material", ""),
                "customer": header.get("customer", ""),
                "region": header.get("region", ""),
                "plant": item.get("plant", ""),
                "requested_qty": schedule.get("requested_qty", ""),
                "confirmed_qty": schedule.get("confirmed_qty", ""),
                "requested_date": schedule.get("requested_date", ""),
                "schedule_date": schedule.get("schedule_date", ""),
                "schedule_status": schedule.get("schedule_status", ""),
                "atp_check_result": schedule.get("atp_check_result", ""),
                "reason_code": reason_code,
                "reason_text": reason_text,
                "contributing_reasons": contributing_reasons,
                "snapshot_last_bop_timestamp": last_bop.get("log_timestamp", ""),
                "snapshot_last_bop_status": last_bop.get("bop_status", ""),
                "snapshot_last_bop_message": last_bop.get("bop_message", ""),
            }
        )

    return {"sales_order": so_number, "header": header, "mode": "snapshot", "results": results}


def current_state_check_sales_order(
    so_number: str,
    store: DataStore,
    snapshot_store: DataStore | None = None,
) -> dict[str, Any]:
    """Recompute schedule state against the current data picture."""
    baseline_store = snapshot_store if snapshot_store is not None else store
    snapshot = snapshot_sales_order(so_number, baseline_store)
    if snapshot.get("message"):
        return snapshot

    current = troubleshoot_sales_order(so_number, store)
    current_map = {
        (r.get("sales_order", ""), r.get("item_number", ""), r.get("schedule_line", "")): r
        for r in current.get("results", [])
    }

    compared: list[dict[str, Any]] = []
    for s in snapshot["results"]:
        key = (s.get("sales_order", ""), s.get("item_number", ""), s.get("schedule_line", ""))
        c = current_map.get(key, {})
        requested_date = s.get("requested_date", "")
        projected_current_schedule_date = _project_current_schedule_date(c, s)
        can_meet = bool(projected_current_schedule_date) and (
            not requested_date or projected_current_schedule_date <= requested_date
        ) and not str(c.get("reason_code", "")).startswith("NO_SCHEDULE")

        compared.append(
            {
                **s,
                "current_reason_code": c.get("reason_code", ""),
                "current_reason_text": c.get("reason_text", ""),
                "current_schedule_date": projected_current_schedule_date,
                "current_schedule_date_raw": c.get("schedule_date", ""),
                "current_confirmed_qty": c.get("confirmed_qty", ""),
                "current_contributing_reasons": _normalize_contributing_reasons(
                    (
                        c.get("contributing_reasons", [])
                        if c.get("contributing_reasons", [])
                        else _fallback_contributing_reason(
                            c.get("reason_code", ""),
                            c.get("reason_text", ""),
                        )
                    )
                ),
                "can_meet_requested_date_now": can_meet,
                "status_changed": (
                    s.get("reason_code", "") != c.get("reason_code", "")
                    or s.get("schedule_date", "") != c.get("schedule_date", "")
                ),
                "checked_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }
        )

    return {
        "sales_order": so_number,
        "header": snapshot["header"],
        "mode": "current_check",
        "results": compared,
    }
