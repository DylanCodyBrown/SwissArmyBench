"""The made-up sample store (the owner, 2026-11-19: every empty page offers "Try it with sample data"):
three small tables that join (orders -> customers, orders -> products), so a first run has something to
filter, profile, join in SQL and draw in the ERD. Nothing here is real; the same rows every time (no clock,
no randomness). Pure rules, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

FIRST = ("Ada", "Bo", "Cy", "Dee", "Eli", "Fay", "Gus", "Hal", "Ivy", "Jo", "Kit", "Lu")
LAST = ("Fernwood", "Calder", "Marlow", "Ashby", "Brook", "Linden", "Harrow", "Penrose")
CITIES = ("Northvale", "Easton Cove", "Westmere", "Southby", "Kestrel Bay")
PRODUCTS = (
    ("Anvil", "Tools", 42.5),
    ("Bolt pack", "Hardware", 6.25),
    ("Cog", "Hardware", 3.8),
    ("Dowel set", "Wood", 12.0),
    ("Easel", "Art", 58.0),
    ("File", "Tools", 9.9),
    ("Gouache", "Art", 15.5),
    ("Hinge", "Hardware", 4.4),
)
CUSTOMERS = 24
ORDERS = 120


@dataclass(frozen=True)
class SampleTable:
    """One table of the sample: its name, its columns, its rows, the columns that hold ISO dates."""

    name: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    dates: tuple[str, ...] = ()


def store() -> tuple[SampleTable, ...]:
    """The sample store, the one side first (customers, products), then the orders that point at them."""
    customers = tuple(
        (
            i + 1,
            f"{FIRST[i % len(FIRST)]} {LAST[(i * 3) % len(LAST)]}",
            CITIES[(i * 7) % len(CITIES)],
            f"2025-{(i % 12) + 1:02d}-{(i * 5) % 27 + 1:02d}",
        )
        for i in range(CUSTOMERS)
    )
    products = tuple((i + 101, name, category, price) for i, (name, category, price) in enumerate(PRODUCTS))
    orders = []
    for i in range(ORDERS):
        product = (i * 5) % len(PRODUCTS)
        quantity = (i * 7) % 9 + 1
        price = PRODUCTS[product][2]
        orders.append(
            (
                5001 + i,
                (i * 11) % CUSTOMERS + 1,
                product + 101,
                quantity,
                round(price * quantity, 2),
                f"2026-{(i % 10) + 1:02d}-{(i * 3) % 28 + 1:02d}",
                ("shipped", "shipped", "open", "returned")[i % 4],
            )
        )
    return (
        SampleTable("customers", ("customer_id", "name", "city", "joined"), customers, ("joined",)),
        SampleTable("products", ("product_id", "product", "category", "price"), products),
        SampleTable(
            "orders",
            ("order_id", "customer_id", "product_id", "quantity", "amount", "order_date", "status"),
            tuple(orders),
            ("order_date",),
        ),
    )
