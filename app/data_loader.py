from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import pandas as pd


DATA_FILES = {
    "sales_orders": "sales_orders.csv",
    "sales_order_items": "sales_order_items.csv",
    "sales_order_schedules": "sales_order_schedules.csv",
    "stock_supply": "stock_supply.csv",
    "allocations": "allocations.csv",
    "deliveries": "deliveries.csv",
    "planned_orders": "planned_orders.csv",
    "bop_logs": "bop_logs.csv",
    "plant_substitutions": "plant_substitutions.csv",
}


def _as_float(value: str | int | float | None) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def _wildcard_to_regex(pattern: str) -> str:
    escaped = re.escape(pattern)
    # Support shell-style wildcards and SQL-like wildcard aliases.
    escaped = escaped.replace(r"\*", ".*").replace(r"\?", ".")
    escaped = escaped.replace(r"\%", ".*").replace(r"\_", ".")
    return f"^{escaped}$"


def _match_mask(series: pd.Series, raw_filter: str | None) -> pd.Series:
    normalized = str(raw_filter or "").strip()
    if normalized == "":
        return pd.Series([True] * len(series), index=series.index)

    values = series.fillna("").astype(str)
    has_wildcard = any(token in normalized for token in ("*", "?", "%", "_"))
    if has_wildcard:
        regex = _wildcard_to_regex(normalized)
        return values.str.match(regex, case=False, na=False)

    return values.str.lower() == normalized.lower()


def _sorted_unique_non_empty(series: pd.Series) -> list[str]:
    values = [str(v).strip() for v in series.fillna("").astype(str).tolist()]
    unique_values = {v for v in values if v}
    return sorted(unique_values, key=lambda v: v.lower())


@dataclass
class DataStore:
    sales_orders: pd.DataFrame
    sales_order_items: pd.DataFrame
    sales_order_schedules: pd.DataFrame
    stock_supply: pd.DataFrame
    allocations: pd.DataFrame
    deliveries: pd.DataFrame
    planned_orders: pd.DataFrame
    bop_logs: pd.DataFrame
    plant_substitutions: pd.DataFrame

    @classmethod
    def load(cls, data_dir: Path) -> "DataStore":
        data: dict[str, pd.DataFrame] = {}

        for key, filename in DATA_FILES.items():
            path = data_dir / filename
            if path.exists():
                data[key] = pd.read_csv(path, dtype=str).fillna("")
            else:
                data[key] = pd.DataFrame()

        return cls(**data)

    def counts(self) -> dict[str, int]:
        return {name: len(getattr(self, name)) for name in DATA_FILES}

    def subset_by_orders(self, allowed_orders: set[str]) -> "DataStore":
        """
        Build a store containing only rows tied to the provided sales orders for
        order-linked datasets. Non-order datasets are preserved as-is.
        """
        data: dict[str, pd.DataFrame] = {}
        for key in DATA_FILES:
            df = getattr(self, key)
            if df.empty:
                data[key] = df.copy()
                continue
            if "sales_order" in df.columns:
                data[key] = df[df["sales_order"].isin(allowed_orders)].copy()
            else:
                data[key] = df.copy()
        return DataStore(**data)

    def dataset_keys(self) -> list[str]:
        return list(DATA_FILES.keys())

    def dataset_filename(self, dataset_name: str) -> str:
        return DATA_FILES[dataset_name]

    def dataset_preview(self, dataset_name: str) -> dict[str, Any]:
        if dataset_name not in DATA_FILES:
            raise KeyError(f"Unknown dataset: {dataset_name}")

        df = getattr(self, dataset_name)
        if df.empty:
            return {"columns": [], "rows": [], "row_count": 0}

        return {
            "columns": list(df.columns),
            "rows": df.to_dict(orient="records"),
            "row_count": len(df),
        }

    def filter_sales_orders(
        self,
        sales_order: str | None = None,
        customer: str | None = None,
        material: str | None = None,
        plant: str | None = None,
        only_not_fully_on_request_date: bool = False,
    ) -> list[dict[str, Any]]:
        if self.sales_orders.empty:
            return []

        df = self.sales_orders.copy()
        if sales_order:
            # Keep SO query behavior consistent with detail-link navigation.
            df = df[_match_mask(df["sales_order"], sales_order)]

        # If an SO is explicitly provided, treat it as the primary selector
        # so text-box query flow matches SO hyperlink drilldown behavior.
        if not sales_order:
            if customer:
                df = df[_match_mask(df["customer"], customer)]

            if material or plant:
                if self.sales_order_items.empty:
                    return []
                items = self.sales_order_items.copy()
                if material:
                    items = items[_match_mask(items["material"], material)]
                if plant:
                    items = items[_match_mask(items["plant"], plant)]
                allowed_orders = set(items["sales_order"].tolist())
                df = df[df["sales_order"].isin(allowed_orders)]

        if only_not_fully_on_request_date:
            allowed_orders = self.not_fully_scheduled_on_request_date_order_set()
            df = df[df["sales_order"].isin(allowed_orders)]

        return df.to_dict(orient="records")

    def not_fully_scheduled_on_request_date_order_set(self) -> set[str]:
        """
        Orders where at least one schedule line is not fully scheduled on requested date.
        """
        if self.sales_order_schedules.empty:
            return set()

        flagged_orders: set[str] = set()
        for schedule in self.sales_order_schedules.to_dict(orient="records"):
            so = str(schedule.get("sales_order", "") or "")
            if not so:
                continue

            requested_qty = _as_float(schedule.get("requested_qty"))
            confirmed_qty = _as_float(schedule.get("confirmed_qty"))
            requested_date = str(schedule.get("requested_date", "") or "")
            schedule_date = str(schedule.get("schedule_date", "") or "")
            reason_code = str(schedule.get("reason_code_expected", "") or "")
            schedule_status = str(schedule.get("schedule_status", "") or "")

            is_fully_scheduled_on_request_date = (
                requested_qty > 0
                and confirmed_qty >= requested_qty
                and requested_date != ""
                and schedule_date != ""
                and schedule_date <= requested_date
                and not reason_code.startswith("NO_SCHEDULE")
                and schedule_status != "UNCONFIRMED"
            )
            if not is_fully_scheduled_on_request_date:
                flagged_orders.add(so)

        return flagged_orders

    def order_parts_map(self) -> dict[str, str]:
        """Map sales order -> comma-separated unique parts from item rows."""
        if self.sales_order_items.empty:
            return {}

        parts_by_order: dict[str, set[str]] = {}
        for item in self.sales_order_items.to_dict(orient="records"):
            so = str(item.get("sales_order", "") or "")
            material = str(item.get("material", "") or "")
            if not so or not material:
                continue
            if so not in parts_by_order:
                parts_by_order[so] = set()
            parts_by_order[so].add(material)

        return {so: ", ".join(sorted(parts)) for so, parts in parts_by_order.items()}

    def sales_order_bundle(self, so_number: str) -> dict[str, Any]:
        so_normalized = str(so_number or "").strip().lower()
        header = (
            self.sales_orders[self.sales_orders["sales_order"].astype(str).str.lower() == so_normalized]
            if not self.sales_orders.empty
            else pd.DataFrame()
        )
        items = (
            self.sales_order_items[
                self.sales_order_items["sales_order"].astype(str).str.lower() == so_normalized
            ]
            if not self.sales_order_items.empty
            else pd.DataFrame()
        )
        schedules = (
            self.sales_order_schedules[
                self.sales_order_schedules["sales_order"].astype(str).str.lower() == so_normalized
            ]
            if not self.sales_order_schedules.empty
            else pd.DataFrame()
        )
        return {
            "header": header.to_dict(orient="records"),
            "items": items.to_dict(orient="records"),
            "schedules": schedules.to_dict(orient="records"),
        }

    def query_lov_options(self) -> dict[str, list[str]]:
        """Searchable LOV suggestions for query inputs."""
        sales_orders = (
            _sorted_unique_non_empty(self.sales_orders["sales_order"])
            if not self.sales_orders.empty and "sales_order" in self.sales_orders.columns
            else []
        )
        customers = (
            _sorted_unique_non_empty(self.sales_orders["customer"])
            if not self.sales_orders.empty and "customer" in self.sales_orders.columns
            else []
        )
        materials = (
            _sorted_unique_non_empty(self.sales_order_items["material"])
            if not self.sales_order_items.empty and "material" in self.sales_order_items.columns
            else []
        )
        plants = (
            _sorted_unique_non_empty(self.sales_order_items["plant"])
            if not self.sales_order_items.empty and "plant" in self.sales_order_items.columns
            else []
        )
        return {
            "sales_order": sales_orders,
            "customer": customers,
            "material": materials,
            "plant": plants,
        }

    def delayed_order_set(self) -> set[str]:
        """Orders with at least one schedule date pushed past requested date."""
        if self.sales_order_schedules.empty:
            return set()

        df = self.sales_order_schedules.copy()
        df = df[(df["requested_date"] != "") & (df["schedule_date"] != "")]
        df = df[df["schedule_date"] > df["requested_date"]]
        return set(df["sales_order"].tolist())

    def order_scheduled_date_map(self) -> dict[str, str]:
        """
        Derive order-level scheduled date for the main list.
        Uses the earliest non-empty schedule date across all schedule lines.
        """
        if self.sales_order_schedules.empty:
            return {}

        df = self.sales_order_schedules.copy()
        df = df[df["schedule_date"] != ""]
        if df.empty:
            return {}

        grouped = df.groupby("sales_order")["schedule_date"].min()
        return {str(so): str(date) for so, date in grouped.to_dict().items()}

    def order_row_class_map(self) -> dict[str, str]:
        """
        Derive row class for main order list from schedule lines.
        Priority: unscheduled (red) > delayed (amber) > none.
        """
        if self.sales_order_schedules.empty:
            return {}

        row_class_by_order: dict[str, str] = {}
        for schedule in self.sales_order_schedules.to_dict(orient="records"):
            so = schedule.get("sales_order", "")
            if not so:
                continue

            reason_code = schedule.get("reason_code_expected", "") or ""
            schedule_date = schedule.get("schedule_date", "") or ""
            requested_date = schedule.get("requested_date", "") or ""
            schedule_status = schedule.get("schedule_status", "") or ""

            is_unscheduled = (
                schedule_date == ""
                or schedule_status == "UNCONFIRMED"
                or reason_code.startswith("NO_SCHEDULE")
            )
            is_delayed = (
                not is_unscheduled
                and schedule_date != ""
                and requested_date != ""
                and schedule_date > requested_date
            )

            current = row_class_by_order.get(so, "")
            if is_unscheduled:
                row_class_by_order[so] = "row-unscheduled"
            elif is_delayed and current != "row-unscheduled":
                row_class_by_order[so] = "row-delayed"
            elif so not in row_class_by_order:
                row_class_by_order[so] = ""

        return row_class_by_order
