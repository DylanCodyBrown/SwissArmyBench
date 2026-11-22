"""Made-up data for the field service test app (examples/field_service): Brightline Field Services, a
company that does not exist. Six small tables, the same rows every time (no clock, no random module: a
small arithmetic recipe), with a few deliberate things for the app's patterns to find: an invoice whose
amount is off, an invoice with no work order, work orders with no invoice, a price list with versions."""

from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path
from typing import Any

REGIONS = ["North", "South", "East", "West"]
SKILLS = ["HVAC", "Electrical", "Plumbing", "Refrigeration"]
STATUSES = ["open", "scheduled", "in_progress", "done", "done", "done", "cancelled"]
PRIORITIES = ["low", "normal", "normal", "high"]
FIRST = ["Ada", "Bram", "Cleo", "Dov", "Esme", "Finn", "Greta", "Hugo", "Ines", "Jory", "Kaia", "Lev"]
LAST = ["Marlow", "Quill", "Tarn", "Voss", "Wren", "Yarrow"]
PLACES = ["Alderbrook", "Fennick", "Greywater", "Hollin", "Marsh End", "Oakhollow", "Pellham", "Runswick"]
TRADES = ["Bakery", "Clinic", "Dairy", "Hotel", "Laundry", "Market", "School", "Workshop"]
PARTS = [
    ("FLT-100", "Air filter", 12.5),
    ("CMP-220", "Compressor relay", 48.0),
    ("VLV-310", "Shut-off valve", 21.75),
    ("THM-415", "Thermostat", 64.0),
    ("FAN-520", "Fan motor", 115.0),
    ("SEA-610", "Door seal", 9.25),
]
DAY0 = date(2026, 7, 1)
ORDERS = 120


def technicians() -> list[dict[str, Any]]:
    return [
        {
            "technician_id": 100 + n,
            "name": f"{FIRST[n]} {LAST[n % len(LAST)]}",
            "region": REGIONS[n % 4],
            "skill": SKILLS[(n * 3) % 4],
            "active": n != 7,
        }
        for n in range(12)
    ]


def customers() -> list[dict[str, Any]]:
    return [
        {
            "customer_id": 500 + n,
            "name": f"{PLACES[n % 8]} {TRADES[(n * 5 + n // 8) % 8]}",
            "city": PLACES[(n * 3) % 8],
            "region": REGIONS[(n // 2) % 4],
        }
        for n in range(24)
    ]


def work_orders() -> list[dict[str, Any]]:
    rows = []
    for n in range(ORDERS):
        status = STATUSES[(n * 5) % len(STATUSES)]
        opened = DAY0 + timedelta(days=(n * 7) % 120)
        hours = round(1 + ((n * 37) % 28) / 4, 2)
        done = status == "done"
        rows.append(
            {
                "work_order_id": 1000 + n,
                "customer_id": 500 + (n * 11) % 24,
                "technician_id": 100 + (n * 5) % 12,
                "region": REGIONS[(((n * 11) % 24) // 2) % 4],
                "status": status,
                "priority": PRIORITIES[(n * 3) % 4],
                "opened_on": opened.isoformat(),
                "closed_on": (opened + timedelta(days=1 + n % 5)).isoformat() if done else "",
                "hours": hours if status in ("done", "in_progress") else 0.0,
                "amount": round(hours * 85 + (n % 6) * 12.5, 2) if done else 0.0,
                "summary": f"{SKILLS[n % 4]} visit: {PARTS[n % 6][1].lower()} check",
            }
        )
    return rows


def parts_used() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for n in range(ORDERS):
        if STATUSES[(n * 5) % len(STATUSES)] != "done":
            continue
        for k in range(1 + n % 2):
            sku, _, cost = PARTS[(n + k * 2) % 6]
            rows.append(
                {
                    "line_id": len(rows) + 1,
                    "work_order_id": 1000 + n,
                    "part_sku": sku,
                    "quantity": 1 + (n + k) % 3,
                    "unit_cost": cost,
                }
            )
    return rows


def price_lists() -> list[dict[str, Any]]:
    """Each part's price in three versions (the third the current one)."""
    rows = []
    for sku, name, cost in PARTS:
        for version in (1, 2, 3):
            rows.append(
                {
                    "price_id": f"{sku}-v{version}",
                    "part_sku": sku,
                    "part_name": name,
                    "version": version,
                    "is_current": version == 3,
                    "price": round(cost * (1.2 + version / 10), 2),
                }
            )
    return rows


# What reconciling the invoices against the done work orders must say (by work_order_id, on amount).
OFF = (1005, 1012)  # two invoices 10.00 over
NOT_INVOICED = (1114, 1117)  # two done work orders with no invoice
STRAY = 9999  # an invoice whose work order is not there


def invoices() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for order in work_orders():
        if order["status"] != "done" or order["work_order_id"] in NOT_INVOICED:
            continue
        rows.append(
            {
                "invoice_id": 7000 + len(rows),
                "work_order_id": order["work_order_id"],
                "invoiced_on": order["closed_on"],
                "amount": round(order["amount"] + (10 if order["work_order_id"] in OFF else 0), 2),
            }
        )
    rows.append({"invoice_id": 7999, "work_order_id": STRAY, "invoiced_on": "2026-10-30", "amount": 42.0})
    return rows


TABLES = {
    "technicians": technicians,
    "customers": customers,
    "work_orders": work_orders,
    "parts_used": parts_used,
    "price_lists": price_lists,
    "invoices": invoices,
}


def write_csv(folder: Path, name: str) -> Path:
    """One table as <folder>/<name>.csv (the app reads its types)."""
    rows = TABLES[name]()
    path = folder / f"{name}.csv"
    with path.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_all(folder: Path) -> dict[str, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    return {name: write_csv(folder, name) for name in TABLES}
