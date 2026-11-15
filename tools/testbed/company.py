"""A made-up small company for the real-world test bed: Quillmere Supply, which sells shelving, desk
goods, tools, packaging, lighting and paper to shops and workshops. Nothing here is real: every name,
town and address is invented, every email is at example.com, and the rows come from a seed, so each run
is the same.

    customers     60, each in one of four regions and three segments
    products      36, in six categories, with a SKU, a price and a cost
    orders        about 1,500 from 2025-11-01 to 2026-10-31, as they land from the web shop: a status
                  written several ways (" Shipped", "SHIPPED", "shipped"), a few regions missing, five
                  test orders and eight rows sent twice (the cleaning use case's work)
    order_lines   one to four lines an order
    invoices      one an order that was not cancelled; most paid, some late
    budgets       each department's plan, by month and category
    returns       a few lines sent back (JSON)
    stock         what each warehouse holds of each product

The Power BI stand-in's "Company model" is read from these same rows (one day short: its last refresh
was before the last day's orders), so a tie-out against the database finds the one month that is off.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

SEED = 20261115
FIRST_DAY = date(2025, 11, 1)
LAST_DAY = date(2026, 10, 31)
REGIONS = ("North", "South", "East", "West")
SEGMENTS = ("Retail", "Wholesale", "Online")
TOWNS = {
    "North": ("Quillmere", "Thistleby"),
    "South": ("Copperfold", "Duskwater"),
    "East": ("Marrowgate", "Wrenhallow"),
    "West": ("Larkspur Ridge", "Brackenvale"),
}
_FIRST = ("Alder", "Bramble", "Cobalt", "Driftwood", "Ember", "Fennel", "Granite", "Harbour", "Ivy",
          "Juniper", "Kestrel", "Linden", "Moss", "Nettle", "Oriel", "Pebble", "Quarry", "Rowan",
          "Saffron", "Tamarack")  # fmt: skip
_SECOND = ("Workshop", "Studio", "Supplies", "Traders", "& Co", "Makers", "Outfitters", "Goods",
           "Collective", "Works")  # fmt: skip
CATEGORIES = {
    "Shelving": ("Steel shelf bracket", "Oak wall shelf", "Corner shelf unit", "Shelf pin pack", "Floating shelf", "Pine shelf board"),
    "Desk": ("Desk organiser", "Letter tray", "Pen pot", "Monitor riser", "Cable tidy", "Desk mat"),
    "Tools": ("Claw hammer", "Screwdriver set", "Tape measure", "Utility knife", "Spirit level", "Hex key set"),
    "Packaging": ("Shipping box small", "Shipping box large", "Packing tape", "Bubble wrap roll", "Mailing bag pack", "Void fill paper"),
    "Lighting": ("LED strip", "Desk lamp", "Clip light", "Bulb pack", "Work light", "Night light"),
    "Paper": ("Copy paper ream", "Card stock pack", "Notebook A5", "Sticky notes", "Label sheets", "Kraft paper roll"),
}  # fmt: skip
DEPARTMENTS = ("Sales", "Operations", "Marketing")
WAREHOUSES = ("Quillmere depot", "Copperfold depot")
STATUS_WAYS = {
    "shipped": ("shipped", "Shipped", " Shipped", "SHIPPED ", "shipped "),
    "delivered": ("delivered", "Delivered", "DELIVERED"),
    "pending": ("pending", "Pending "),
    "cancelled": ("cancelled", "Cancelled"),
}


@dataclass(frozen=True)
class Company:
    """Every table of the made-up company, as lists of plain rows."""

    customers: list[dict[str, Any]]
    products: list[dict[str, Any]]
    orders: list[dict[str, Any]]
    order_lines: list[dict[str, Any]]
    invoices: list[dict[str, Any]]
    budgets: list[dict[str, Any]]
    returns: list[dict[str, Any]]
    stock: list[dict[str, Any]]

    def tables(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "customers": self.customers,
            "products": self.products,
            "orders": self.orders,
            "order_lines": self.order_lines,
            "invoices": self.invoices,
            "budgets": self.budgets,
            "returns": self.returns,
            "stock": self.stock,
        }

    def clean_orders(self) -> list[dict[str, Any]]:
        """The orders as the cleaning use case leaves them: status trimmed and lower case, the test
        orders gone, each order once."""
        seen: set[int] = set()
        kept = []
        for order in self.orders:
            if order["status"].strip().lower() == "test" or order["order_id"] in seen:
                continue
            seen.add(order["order_id"])
            kept.append(order | {"status": order["status"].strip().lower()})
        return kept

    def order_amounts(self) -> dict[int, float]:
        """Each order's amount: its lines' quantity times price, less the discount."""
        amounts: dict[int, float] = {}
        for line in self.order_lines:
            amounts[line["order_id"]] = amounts.get(line["order_id"], 0.0) + line_amount(line)
        return {k: round(v, 2) for k, v in amounts.items()}


def line_amount(line: dict[str, Any]) -> float:
    return round(float(line["quantity"] * line["unit_price"] * (1 - line["discount_pct"] / 100)), 2)


def make_company(seed: int = SEED) -> Company:
    rng = random.Random(seed)  # noqa: S311 (made-up rows from a seed, not a secret)
    names = [f"{a} {b}" for a in _FIRST for b in _SECOND]
    rng.shuffle(names)
    customers: list[dict[str, Any]] = []
    for i in range(60):
        home = REGIONS[i % 4]
        name = names[i]
        slug = name.lower().replace("& ", "").replace(" ", "-")
        customers.append(
            {
                "customer_id": 1001 + i,
                "customer_name": name,
                "segment": SEGMENTS[rng.randrange(3)],
                "region": home,
                "town": TOWNS[home][rng.randrange(2)],
                "email": f"accounts@{slug}.example.com",
                "since": FIRST_DAY - timedelta(days=rng.randrange(30, 1500)),
            }
        )
    products: list[dict[str, Any]] = []
    for c, (category, items) in enumerate(CATEGORIES.items()):
        for j, item in enumerate(items):
            price = round(rng.uniform(2.5, 85.0), 2)
            products.append(
                {
                    "product_id": c * 6 + j + 1,
                    "sku": f"QS-{(c + 1) * 100 + j + 1}",
                    "product_name": item,
                    "category": category,
                    "unit_price": price,
                    "unit_cost": round(price * rng.uniform(0.45, 0.7), 2),
                }
            )
    orders: list[dict[str, Any]] = []
    lines: list[dict[str, Any]] = []
    order_id = 50001
    day = FIRST_DAY
    while day <= LAST_DAY:
        # A busier autumn and quieter weekends: a forecast has a season and a trend to find.
        base = 3.2 + 1.4 * (day.month in (9, 10, 11)) + 0.004 * (day - FIRST_DAY).days
        count = max(0, round(base * (0.45 if day.weekday() >= 5 else 1.0) + rng.uniform(-1.2, 1.2)))
        for _ in range(count):
            customer = customers[rng.randrange(60)]
            status = rng.choices(list(STATUS_WAYS), weights=(55, 30, 7, 8))[0]
            if day > LAST_DAY - timedelta(days=6) and status == "delivered":
                status = "shipped"
            region: str | None = customer["region"]
            if rng.random() < 0.02:
                region = None
            orders.append(
                {
                    "order_id": order_id,
                    "customer_id": customer["customer_id"],
                    "order_date": day,
                    "status": rng.choice(STATUS_WAYS[status]),
                    "channel": rng.choice(("web", "web", "phone", "trade counter")),
                    "region": region,
                }
            )
            for line_no in range(1, rng.randint(1, 4) + 1):
                product = products[rng.randrange(len(products))]
                lines.append(
                    {
                        "order_id": order_id,
                        "line_no": line_no,
                        "product_id": product["product_id"],
                        "quantity": rng.randint(1, 12),
                        "unit_price": product["unit_price"],
                        "discount_pct": rng.choice((0, 0, 0, 5, 10)),
                    }
                )
            order_id += 1
        day += timedelta(days=1)
    # The web shop's own test orders, and rows it sent twice.
    for k in range(5):
        orders.append(
            {
                "order_id": 59990 + k,
                "customer_id": 1001,
                "order_date": date(2026, 3, 2 + k),
                "status": "TEST",
                "channel": "web",
                "region": "North",
            }
        )
    for twice in rng.sample(orders[:-5], 8):
        orders.append(dict(twice))
    orders.sort(key=lambda o: (o["order_date"], o["order_id"]))
    amounts: dict[int, float] = {}
    for line in lines:
        amounts[line["order_id"]] = amounts.get(line["order_id"], 0.0) + line_amount(line)
    invoices: list[dict[str, Any]] = []
    regions = {c["customer_id"]: c["region"] for c in customers}
    seen: set[int] = set()
    for order in orders:
        if order["order_id"] in seen or order["status"].strip().lower() in ("cancelled", "test"):
            continue
        seen.add(order["order_id"])
        issued = order["order_date"] + timedelta(days=1)
        due = issued + timedelta(days=30)
        late = rng.random() < 0.12
        paid = (
            None
            if issued > LAST_DAY - timedelta(days=20)
            else due + timedelta(days=rng.randint(1, 40) if late else -rng.randint(0, 25))
        )
        invoices.append(
            {
                "invoice_id": f"INV-{issued.year}-{len(invoices) + 1:05d}",
                "order_id": order["order_id"],
                "customer_id": order["customer_id"],
                "region": regions[order["customer_id"]],
                "invoice_date": issued,
                "due_date": due,
                "amount": round(amounts.get(order["order_id"], 0.0), 2),
                "paid_date": paid,
            }
        )
    budgets: list[dict[str, Any]] = []
    month = date(2025, 11, 1)
    while month <= LAST_DAY:
        for department in DEPARTMENTS:
            for category in CATEGORIES:
                budgets.append(
                    {
                        "department": department,
                        "month": month,
                        "category": category,
                        "planned": float(rng.randrange(800, 4800, 50)),
                    }
                )
        month = date(month.year + month.month // 12, month.month % 12 + 1, 1)
    returns: list[dict[str, Any]] = []
    for k, line in enumerate(rng.sample(lines, 40)):
        returns.append(
            {
                "return_id": 7001 + k,
                "order_id": line["order_id"],
                "product_id": line["product_id"],
                "quantity": rng.randint(1, line["quantity"]),
                "reason": rng.choice(("damaged", "wrong item", "not needed", "late")),
            }
        )
    stock = [
        {"warehouse": w, "product_id": p["product_id"], "on_hand": rng.randrange(0, 400), "reorder_at": 40}
        for w in WAREHOUSES
        for p in products
    ]
    return Company(customers, products, orders, lines, invoices, budgets, returns, stock)
