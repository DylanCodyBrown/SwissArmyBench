"""A made-up retail and wholesale business at three sizes, for testing app pages and local APIs on real
volumes: Larkfield Goods, which sells home, garden, kitchen, tools and office goods through its shops, a
web shop and a phone line, and to trade customers from its depots. Nothing here is real: every name, town
and address is invented, every email is at example.com, and every row comes from the seed.

    regions              8 fixed regions
    stores               a web shop, then shops and depots in each region
    categories           top-level categories and their sub-categories (parent_category_id)
    suppliers            who makes the products (country, lead time, rating)
    products             each in a sub-category, from a supplier, with a price and a cost
    customers            each with a home store and region; a few sent twice (the same person, two ids)
    employees            store staff (a manager each store), head office (regional managers, support)
    orders               skewed (a few customers buy a lot), seasonal (November and December peak), growing
    order_lines          one to five lines an order
    returns              lines sent back after delivery
    inventory_snapshots  month-end stock of the products each store carries
    shipments            one per shipped order: promised and delivered dates, some late, some in transit
    support_tickets      customers' questions, some about an order, open and closed, with an SLA
    data_quality_issues  the deliberate problems, one row each, so a test or a demo can find them

Scales (order lines, about): small 10k, medium 1M, large 10M. Everything is made by DuckDB SQL over
range() with hash-based randomness, so large builds in well under a minute and pandas is never needed;
the same seed and scale give the same rows.

    python -m tools.testbed.large_company --scale large --out /tmp/larkfield
    python -m tools.testbed.large_company --scale small --out /tmp/larkfield --duckdb

From Python: build(out, scale="small") writes the files and returns a Report; generate(connection, ...)
makes the tables in a DuckDB connection of your own (no files).
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb

SEED = 20261121
FIRST_DAY = "2024-11-01"
LAST_DAY = "2026-10-31"  # 24 months
REPOSITORY = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Scale:
    orders: int
    customers: int
    products: int
    stores_per_region: int
    suppliers: int
    staff_per_store: int
    carry_one_in: int  # a store carries about one product in this many (inventory_snapshots)
    tickets_per_100_orders: int
    problems: int  # how many of each deliberate problem


SCALES: dict[str, Scale] = {
    "small": Scale(3_334, 500, 240, 2, 20, 4, 4, 6, 3),
    "medium": Scale(333_334, 40_000, 2_400, 8, 120, 8, 12, 5, 20),
    "large": Scale(3_333_334, 300_000, 12_000, 25, 400, 10, 60, 4, 50),
}

TABLES: tuple[str, ...] = (
    "regions",
    "stores",
    "categories",
    "suppliers",
    "products",
    "customers",
    "employees",
    "orders",
    "order_lines",
    "returns",
    "inventory_snapshots",
    "shipments",
    "support_tickets",
    "data_quality_issues",
)

# Each table's key, and every foreign key as (table, column, referenced table, referenced column).
KEYS: dict[str, tuple[str, ...]] = {
    "regions": ("region_id",),
    "stores": ("store_id",),
    "categories": ("category_id",),
    "suppliers": ("supplier_id",),
    "products": ("product_id",),
    "customers": ("customer_id",),
    "employees": ("employee_id",),
    "orders": ("order_id",),  # not unique on purpose: an order sent twice (data_quality_issues)
    "order_lines": ("order_line_id",),
    "returns": ("return_id",),
    "inventory_snapshots": ("snapshot_date", "store_id", "product_id"),
    "shipments": ("shipment_id",),
    "support_tickets": ("ticket_id",),
    "data_quality_issues": ("issue_id",),
}
FOREIGN_KEYS: tuple[tuple[str, str, str, str], ...] = (
    ("stores", "region_id", "regions", "region_id"),
    ("categories", "parent_category_id", "categories", "category_id"),
    ("products", "category_id", "categories", "category_id"),
    ("products", "supplier_id", "suppliers", "supplier_id"),
    ("customers", "region_id", "regions", "region_id"),
    ("customers", "home_store_id", "stores", "store_id"),
    ("employees", "store_id", "stores", "store_id"),
    ("employees", "manager_id", "employees", "employee_id"),
    ("employees", "region_id", "regions", "region_id"),
    ("orders", "customer_id", "customers", "customer_id"),
    ("orders", "store_id", "stores", "store_id"),
    ("orders", "employee_id", "employees", "employee_id"),
    ("order_lines", "order_id", "orders", "order_id"),
    ("order_lines", "product_id", "products", "product_id"),
    ("returns", "order_line_id", "order_lines", "order_line_id"),
    ("returns", "order_id", "orders", "order_id"),
    ("inventory_snapshots", "store_id", "stores", "store_id"),
    ("inventory_snapshots", "product_id", "products", "product_id"),
    ("shipments", "order_id", "orders", "order_id"),
    ("support_tickets", "customer_id", "customers", "customer_id"),
    ("support_tickets", "order_id", "orders", "order_id"),
    ("support_tickets", "assigned_employee_id", "employees", "employee_id"),
)

_REGIONS = (
    ("North Vale", "Northmark", "Europe/Berlin"),
    ("South Reach", "Northmark", "Europe/Berlin"),
    ("East Fen", "Northmark", "Europe/Berlin"),
    ("West Downs", "Northmark", "Europe/Berlin"),
    ("Coastline", "Southmere", "Europe/Lisbon"),
    ("Highlands", "Southmere", "Europe/Lisbon"),
    ("Lakeside", "Eastholm", "Europe/Helsinki"),
    ("Riverlands", "Eastholm", "Europe/Helsinki"),
)
_CATEGORIES = {
    "Home": ("Lighting", "Storage", "Textiles"),
    "Garden": ("Planters", "Garden tools", "Outdoor furniture"),
    "Kitchen": ("Cookware", "Tableware", "Small appliances"),
    "Tools": ("Hand tools", "Power tools", "Fixings"),
    "Office": ("Paper", "Desk goods", "Packaging"),
}


def _list(words: tuple[str, ...] | list[str]) -> str:
    return "[" + ", ".join("'" + w.replace("'", "''") + "'" for w in words) + "]"


_TOWNS = _list(
    ("Ashbourne Mill", "Briarwick", "Cindermoor", "Dunhollow", "Elmstead Cross", "Fernhaven", "Glimmerdale",
     "Hollowmere", "Ironbridge Vale", "Juniper Bay", "Kettlewick", "Larkfield", "Marshby", "Nettlecombe",
     "Oakhurst Green", "Pennydown", "Quarrytown", "Ravensholt", "Saltmarsh End", "Thornbury Rise")
)  # fmt: skip
_FIRST = _list(
    ("Ada", "Bram", "Cleo", "Dov", "Esme", "Finn", "Greta", "Hugo", "Ines", "Jory", "Kaia", "Lior", "Mira",
     "Nico", "Odile", "Pim", "Quinn", "Rosa", "Sven", "Tilde", "Umar", "Vera", "Wim", "Xena", "Yara", "Zeno")
)  # fmt: skip
_LAST = _list(
    ("Ashdown", "Brookfield", "Calloway", "Dunmore", "Everly", "Fairbank", "Greenleaf", "Hartwell",
     "Ironside", "Jessup", "Kingsley", "Lockwood", "Marlow", "Northcott", "Oakley", "Pemberton", "Quill",
     "Rowntree", "Sterling", "Thorne", "Underhill", "Vance", "Whitlock", "Yardley")
)  # fmt: skip
_TRADE = _list(("Workshop", "Interiors", "Builders", "Garden Co", "Kitchens", "Supplies", "& Sons", "Studio"))
_ADJECTIVES = _list(
    ("Classic", "Compact", "Deluxe", "Eco", "Everyday", "Heavy-duty", "Large", "Mini", "Nordic", "Pro",
     "Rustic", "Slim", "Smart", "Soft", "Steel", "Oak", "Bamboo", "Ceramic", "Linen", "Copper")
)  # fmt: skip
_NOUNS = {
    "Lighting": ("Desk lamp", "Floor lamp", "LED strip", "Pendant light", "Bulb pack"),
    "Storage": ("Storage box", "Shelf unit", "Basket", "Drawer set", "Hook rail"),
    "Textiles": ("Cushion", "Throw", "Rug", "Curtain pair", "Tea towel set"),
    "Planters": ("Planter", "Window box", "Hanging pot", "Raised bed", "Seed tray"),
    "Garden tools": ("Trowel", "Pruner", "Rake", "Hose reel", "Watering can"),
    "Outdoor furniture": ("Bench", "Bistro set", "Lounger", "Parasol", "Side table"),
    "Cookware": ("Frying pan", "Saucepan", "Casserole", "Wok", "Roasting tin"),
    "Tableware": ("Dinner plate set", "Bowl set", "Mug pair", "Glass set", "Cutlery set"),
    "Small appliances": ("Kettle", "Toaster", "Blender", "Hand mixer", "Coffee grinder"),
    "Hand tools": ("Claw hammer", "Screwdriver set", "Spirit level", "Hand saw", "Hex key set"),
    "Power tools": ("Drill driver", "Jigsaw", "Orbital sander", "Impact driver", "Heat gun"),
    "Fixings": ("Screw pack", "Wall plug pack", "Bracket", "Hinge pair", "Bolt set"),
    "Paper": ("Copy paper ream", "Notebook", "Sticky notes", "Label sheets", "Card stock"),
    "Desk goods": ("Desk organiser", "Letter tray", "Monitor riser", "Pen pot", "Desk mat"),
    "Packaging": ("Shipping box", "Packing tape", "Bubble wrap", "Mailing bag pack", "Void fill"),
}
# Month weights: the year's season (November and December peak), then a little growth each month.
_SEASON = (0.80, 0.74, 0.90, 0.95, 1.00, 1.00, 0.94, 0.98, 1.05, 1.10, 1.45, 1.75)
_CARRIERS = _list(("Swiftpost", "Parcelwing", "Roadrunner Freight", "Kestrel Couriers"))
_SUBJECTS = _list(
    ("Where is my order?", "Item arrived damaged", "Wrong item sent", "Refund not received",
     "Change delivery address", "Invoice copy please", "Product question", "Cancel my order",
     "Missing part", "Account login problem")
)  # fmt: skip


@dataclass
class Report:
    scale: str
    seed: int
    out: str
    rows: dict[str, int] = field(default_factory=dict)
    seconds: float = 0.0
    files: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "scale": self.scale,
            "seed": self.seed,
            "out": self.out,
            "rows": self.rows,
            "seconds": round(self.seconds, 2),
            "files": self.files,
        }


def _sql(scale: Scale, seed: int) -> list[str]:
    """The statements that make every table, in order. Only whole numbers and fixed words are put into the
    text (the seed and the scale's counts), never a caller's string."""
    s = scale
    seed = int(seed)
    n_regions = len(_REGIONS)
    n_stores = 1 + n_regions * s.stores_per_region  # store 1 is the web shop
    n_staff = (n_stores - 1) * s.staff_per_store
    n_support = max(4, s.customers // 2000)
    # head office: one director, a manager each region, then support agents
    n_employees = n_staff + 1 + n_regions + n_support
    director = n_staff + 1
    months = [(i, _SEASON[(10 + i) % 12] * (1 + 0.012 * i)) for i in range(24)]  # month 0 is November 2024
    total = sum(w for _, w in months)
    cum, rows = 0.0, []
    for i, w in months:
        rows.append(f"({i}, {cum / total!r}, {(cum + w) / total!r})")
        cum += w
    category_rows, sub_id = [], len(_CATEGORIES)
    for top, name in enumerate(_CATEGORIES, start=1):
        category_rows.append(f"({top}, '{name}', NULL)")
    for top, (_name, subs) in enumerate(_CATEGORIES.items(), start=1):
        for sub in subs:
            sub_id += 1
            category_rows.append(f"({sub_id}, '{sub}', {top})")
    n_subs = sub_id - len(_CATEGORIES)
    nouns = "[" + ", ".join(_list(_NOUNS[sub]) for subs in _CATEGORIES.values() for sub in subs) + "]"
    region_rows = ", ".join(
        f"({i}, '{name}', '{country}', '{zone}')" for i, (name, country, zone) in enumerate(_REGIONS, start=1)
    )
    p = s.problems
    return [
        # r(k, salt): a number in [0, 1), the same for the same key, salt and seed
        f"CREATE OR REPLACE TEMP MACRO r(k, salt) AS ((hash(k, salt, {seed}) % 1000003)::DOUBLE / 1000003)",
        "CREATE OR REPLACE TEMP MACRO pick(words, k, salt) AS "
        "(words[1 + floor(r(k, salt) * len(words))::INTEGER])",
        f"CREATE OR REPLACE TABLE regions AS SELECT * FROM (VALUES {region_rows}) "
        "AS t(region_id, region_name, country, timezone)",
        f"CREATE OR REPLACE TABLE categories AS SELECT * FROM (VALUES {', '.join(category_rows)}) "
        "AS t(category_id, category_name, parent_category_id)",
        "CREATE OR REPLACE TABLE stores AS "
        "SELECT 1 AS store_id, 'Larkfield Web Shop' AS store_name, 1 AS region_id, 'Online' AS store_type, "
        "'Larkfield' AS town, DATE '2018-03-01' AS opened_on, NULL::INTEGER AS square_metres, "
        "NULL::DOUBLE AS lat, NULL::DOUBLE AS lon "
        "UNION ALL "
        "SELECT i + 1, pick("
        + _TOWNS
        + ", i, 'town') || CASE WHEN i % 5 = 0 THEN ' Depot' ELSE ' Shop' END, "
        f"1 + (i - 1) % {n_regions}, CASE WHEN i % 5 = 0 THEN 'Depot' ELSE 'Shop' END, "
        "pick(" + _TOWNS + ", i, 'town'), DATE '2012-01-01' + floor(r(i, 'opened') * 4000)::INTEGER, "
        "CASE WHEN i % 5 = 0 THEN 2000 + floor(r(i, 'sqm') * 6000)::INTEGER "
        "ELSE 150 + floor(r(i, 'sqm') * 900)::INTEGER END, "
        f"round(47 + (1 + (i - 1) % {n_regions}) * 0.9 + r(i, 'lat'), 4), "
        f"round(5 + (1 + (i - 1) % {n_regions}) * 1.3 + r(i, 'lon') * 2, 4) "
        f"FROM range(1, {n_stores}) t(i)",
        "CREATE OR REPLACE TABLE suppliers AS SELECT i AS supplier_id, "
        "pick(" + _LAST + ", i, 'sup') || ' ' || pick(['Manufacturing', 'Trading', 'Imports', 'Works', "
        "'Industries'], i, 'sup2') || ' ' || i AS supplier_name, "
        "pick(['Northmark', 'Southmere', 'Eastholm', 'Westerly', 'Farshore'], i, 'country') AS country, "
        "3 + floor(r(i, 'lead') * 40)::INTEGER AS lead_time_days, "
        "round(2.5 + r(i, 'rating') * 2.5, 1) AS rating, "
        "'orders@supplier' || i || '.example.com' AS email "
        f"FROM range(1, {s.suppliers + 1}) t(i)",
        "CREATE OR REPLACE TABLE products AS SELECT i AS product_id, "
        "'LG-' || lpad(i::VARCHAR, 6, '0') AS sku, "
        f"pick({_ADJECTIVES}, i, 'adj') || ' ' || pick({nouns}[sub], i, 'noun') || ' ' || i AS product_name, "
        f"{len(_CATEGORIES)} + sub AS category_id, "
        # a few suppliers make most of the range
        f"1 + floor(pow(r(i, 'supplier'), 2) * {s.suppliers})::INTEGER AS supplier_id, "
        "round(price, 2) AS unit_price, round(price * (0.45 + r(i, 'cost') * 0.3), 2) AS unit_cost, "
        "DATE '2015-01-01' + floor(r(i, 'launch') * 4000)::INTEGER AS launched_on, "
        "r(i, 'disc') < 0.06 AS discontinued, "
        "CASE WHEN r(i, 'wnull') < 0.05 THEN NULL ELSE round(0.1 + r(i, 'w') * 24, 2) END AS weight_kg "
        f"FROM (SELECT i, 1 + floor(r(i, 'sub') * {n_subs})::INTEGER AS sub, "
        "round(exp(1 + r(i, 'price') * 5.5), 2) + 0.99 AS price "
        f"FROM range(1, {s.products + 1}) t(i))",
        # customers: the last few are the same people as earlier ones, sent again (a duplicate record)
        "CREATE OR REPLACE TABLE customers AS SELECT i AS customer_id, "
        "CASE WHEN segment = 'Trade' THEN pick("
        + _LAST
        + ", src, 'last') || ' ' || pick("
        + _TRADE
        + ", src, 'trade') ELSE pick("
        + _FIRST
        + ", src, 'first') || ' ' || pick("
        + _LAST
        + ", src, 'last') END AS customer_name, segment, "
        "1 + (home - 2) % " + str(n_regions) + " AS region_id, home AS home_store_id, "
        "'customer' || src || '@example.com' AS email, "
        "CASE WHEN r(src, 'phone') < 0.3 THEN NULL ELSE '+00 ' || lpad((floor(r(src, 'tel') * 1e9))::BIGINT"
        "::VARCHAR, 9, '0') END AS phone, "
        "DATE '2016-01-01' + floor(r(i, 'signup') * 3950)::INTEGER AS signup_date, "
        "pick(['None', 'None', 'Silver', 'Gold', 'Platinum'], src, 'tier') AS loyalty_tier "
        "FROM (SELECT i, src, "
        "CASE WHEN r(src, 'seg') < 0.72 THEN 'Consumer' WHEN r(src, 'seg') < 0.9 THEN 'Trade' "
        "ELSE 'Business' END AS segment, "
        f"2 + floor(r(src, 'home') * {n_stores - 1})::INTEGER AS home "
        f"FROM (SELECT i, CASE WHEN i > {s.customers} THEN (i - {s.customers}) * 7 ELSE i END AS src "
        f"FROM range(1, {s.customers + p + 1}) t(i)))",
        # employees: store staff (k = 0 is the store's manager), then head office
        "CREATE OR REPLACE TABLE employees AS "
        "WITH staff AS (SELECT e, 2 + (e - 1) % " + str(n_stores - 1) + " AS store, "
        f"(e - 1) // {n_stores - 1} AS k FROM range(1, {n_staff + 1}) t(e)) "
        "SELECT e AS employee_id, pick("
        + _FIRST
        + ", e, 'efirst') || ' ' || pick("
        + _LAST
        + ", e, 'elast') AS full_name, "
        "CASE WHEN k = 0 THEN 'Store manager' WHEN k % 3 = 1 THEN 'Sales associate' "
        "WHEN k % 3 = 2 THEN 'Stock clerk' ELSE 'Cashier' END AS role, store AS store_id, "
        f"1 + (store - 2) % {n_regions} AS region_id, "
        f"CASE WHEN k = 0 THEN {director} + 1 + (store - 2) % {n_regions} ELSE store - 1 END AS manager_id, "
        "DATE '2012-01-01' + floor(r(e, 'hired') * 5000)::INTEGER AS hired_on, "
        "'staff' || e || '@larkfield.example.com' AS email, r(e, 'left') > 0.07 AS active FROM staff "
        "UNION ALL SELECT e, pick(" + _FIRST + ", e, 'efirst') || ' ' || pick(" + _LAST + ", e, 'elast'), "
        f"CASE WHEN e = {director} THEN 'Director' WHEN e <= {director + n_regions} THEN 'Regional manager' "
        "ELSE 'Support agent' END, NULL, "
        f"CASE WHEN e = {director} THEN NULL WHEN e <= {director + n_regions} THEN e - {director} "
        "ELSE NULL END, "
        f"CASE WHEN e = {director} THEN NULL ELSE {director} END, "
        "DATE '2012-01-01' + floor(r(e, 'hired') * 5000)::INTEGER, "
        "'staff' || e || '@larkfield.example.com', true "
        f"FROM range({director}, {n_employees + 1}) t(e)",
        f"CREATE OR REPLACE TEMP TABLE month_weights AS SELECT * FROM (VALUES {', '.join(rows)}) "
        "AS t(m, lo, hi)",
        # a month for each of 10,000 buckets of [0, 1), so an order finds its month by an equal join
        "CREATE OR REPLACE TEMP TABLE month_buckets AS SELECT b, m FROM range(10000) t(b) "
        "JOIN month_weights w ON (b + 0.5) / 10000 >= w.lo AND (b + 0.5) / 10000 < w.hi",
        # orders: skewed customers (low ids buy most), seasonal months, a channel, a status by age
        "CREATE OR REPLACE TABLE orders AS "
        "WITH base AS (SELECT o, "
        f"1 + floor(pow(r(o, 'cust'), 2.6) * {s.customers})::INTEGER AS customer_id, "
        "r(o, 'month') AS rm, r(o, 'channel') AS rc FROM range(1, " + str(s.orders + 1) + ") t(o)), "
        "dated AS (SELECT b.*, (DATE '" + FIRST_DAY + "' + to_months(w.m))::DATE "
        "+ floor(r(o, 'day') * 28)::INTEGER AS order_date FROM base b "
        "JOIN month_buckets w ON w.b = floor(b.rm * 10000)::BIGINT), "
        "placed AS (SELECT d.*, c.home_store_id, c.segment, "
        "CASE WHEN rc < 0.32 THEN 'Online' WHEN rc < 0.42 THEN 'Phone' ELSE 'Store' END AS channel "
        "FROM dated d JOIN customers c USING (customer_id)), "
        "stored AS (SELECT *, CASE WHEN channel = 'Online' THEN 1 WHEN r(o, 'away') < 0.75 "
        f"THEN home_store_id ELSE 2 + floor(r(o, 'other') * {n_stores - 1})::INTEGER END AS store_id "
        "FROM placed) "
        "SELECT o AS order_id, customer_id, store_id, "
        f"CASE WHEN channel = 'Online' THEN NULL ELSE store_id + {n_stores - 1} * "
        f"floor(r(o, 'emp') * {s.staff_per_store})::INTEGER - 1 END AS employee_id, "
        "order_date, channel, "
        "CASE WHEN r(o, 'cancel') < 0.03 THEN 'cancelled' "
        "WHEN DATE '" + LAST_DAY + "' - order_date < 3 THEN 'pending' "
        "WHEN DATE '" + LAST_DAY + "' - order_date < 10 THEN 'shipped' ELSE 'delivered' END AS status, "
        "CASE WHEN segment = 'Trade' OR channel = 'Store' THEN 0.0 ELSE 4.95 END AS shipping_fee, "
        "order_date::TIMESTAMP + INTERVAL 1 DAY + to_seconds(floor(r(o, 'load') * 3600)::BIGINT) "
        "AS loaded_at FROM stored",
        # order lines: one to five an order (order_line_id is order_id * 8 + line_no); popular products sell
        # more; a discount sometimes
        "CREATE OR REPLACE TABLE order_lines AS "
        "SELECT o.order_id * 8 + n AS order_line_id, o.order_id, n AS line_no, "
        "p.product_id, q AS quantity, p.unit_price, d AS discount_pct, "
        "round(q * p.unit_price * (1 - d / 100.0), 2) AS line_total FROM "
        "(SELECT order_id, n, "
        f"1 + floor(pow(r(order_id * 8 + n, 'prod'), 2) * {s.products})::INTEGER AS pid, "
        "CASE WHEN r(order_id * 8 + n, 'qty') < 0.6 THEN 1 ELSE 1 + floor(pow(r(order_id * 8 + n, 'qty2'), "
        "3) * 24)::INTEGER END AS q, "
        "pick([0, 0, 0, 0, 5, 10, 15, 20], order_id * 8 + n, 'disc') AS d "
        f"FROM range(1, {s.orders + 1}) t(order_id), range(1, 6) u(n) "
        "WHERE n <= 1 + floor(r(order_id, 'lines') * 5)) o "
        "JOIN products p ON p.product_id = o.pid",
        # deliberate problems: a few order lines with a negative quantity
        "CREATE OR REPLACE TEMP TABLE dq_negative AS SELECT order_line_id FROM order_lines "
        f"ORDER BY r(order_line_id, 'neg') LIMIT {p}",
        "UPDATE order_lines SET quantity = -quantity, line_total = -line_total "
        "WHERE order_line_id IN (SELECT order_line_id FROM dq_negative)",
        # a few orders that arrived late (loaded six weeks after they were placed)
        "CREATE OR REPLACE TEMP TABLE dq_late AS SELECT order_id FROM orders "
        f"WHERE status = 'delivered' ORDER BY r(order_id, 'late') LIMIT {p}",
        "UPDATE orders SET loaded_at = loaded_at + INTERVAL 41 DAY "
        "WHERE order_id IN (SELECT order_id FROM dq_late)",
        "CREATE OR REPLACE TABLE shipments AS "
        "SELECT row_number() OVER (ORDER BY order_id) AS shipment_id, order_id, "
        f"pick({_CARRIERS}, order_id, 'carrier') AS carrier, shipped_on, promised_on, "
        "CASE WHEN status = 'shipped' THEN NULL ELSE shipped_on + transit END AS delivered_on, "
        "CASE WHEN status = 'shipped' THEN 'In transit' WHEN shipped_on + transit > promised_on THEN 'Late' "
        "ELSE 'On time' END AS status, "
        "printf('%012X', hash(order_id, 'track', " + str(seed) + ") % 281474976710656) AS tracking_code "
        "FROM (SELECT order_id, status, order_date + floor(r(order_id, 'ship') * 3)::INTEGER "
        "AS shipped_on, order_date + 3 + floor(r(order_id, 'promise') * 5)::INTEGER AS promised_on, "
        "1 + floor(pow(r(order_id, 'transit'), 1.8) * 9)::INTEGER AS transit FROM orders "
        "WHERE status IN ('shipped', 'delivered'))",
        # a few deliveries before they were shipped (a clock set wrong at a depot)
        "CREATE OR REPLACE TEMP TABLE dq_early AS SELECT shipment_id FROM shipments "
        f"WHERE delivered_on IS NOT NULL ORDER BY r(shipment_id, 'early') LIMIT {p}",
        "UPDATE shipments SET delivered_on = shipped_on - 2, status = 'On time' "
        "WHERE shipment_id IN (SELECT shipment_id FROM dq_early)",
        "CREATE OR REPLACE TABLE returns AS "
        "SELECT row_number() OVER (ORDER BY l.order_line_id) AS return_id, l.order_line_id, l.order_id, "
        "o.order_date + 5 + floor(r(l.order_line_id, 'rday') * 25)::INTEGER AS returned_on, "
        "1 + floor(r(l.order_line_id, 'rqty') * l.quantity)::INTEGER AS quantity, "
        "pick(['Damaged', 'Wrong item', 'Not needed', 'Arrived late', 'Not as described'], "
        "l.order_line_id, 'reason') AS reason, "
        "round(l.line_total / l.quantity * (1 + floor(r(l.order_line_id, 'rqty') * l.quantity)), 2) "
        "AS refund_amount FROM order_lines l "
        "JOIN orders o USING (order_id) "
        "WHERE o.status = 'delivered' AND l.quantity > 0 AND r(l.order_line_id, 'ret') < 0.04 "
        "AND o.order_date + 30 <= DATE '" + LAST_DAY + "'",
        "CREATE OR REPLACE TABLE inventory_snapshots AS "
        "SELECT last_day(DATE '" + FIRST_DAY + "' + to_months(12 + m)) AS snapshot_date, s AS store_id, "
        "p AS product_id, "
        "CASE WHEN r((s * 100000 + p) * 16 + m, 'out') < 0.06 THEN 0 ELSE floor(r((s * 100000 + p) * 16 + m, 'onhand') * 220)"
        "::INTEGER END AS on_hand, "
        "CASE WHEN r((s * 100000 + p) * 16 + m, 'order') < 0.3 THEN 24 + floor(r(s * 100000 + p, 'order2') * 4) * 24 "
        "ELSE 0 END::INTEGER AS on_order, "
        "10 + floor(r(s * 100000 + p, 'reorder') * 50)::INTEGER AS reorder_point "
        f"FROM range(1, {n_stores + 1}) t(s), range(1, {s.products + 1}) u(p), range(0, 12) v(m) "
        f"WHERE r(s * 100000 + p, 'carry') < {1 / s.carry_one_in!r}",
        "CREATE OR REPLACE TABLE support_tickets AS "
        "WITH t AS (SELECT k, "
        f"1 + floor(pow(r(k, 'tcust'), 2) * {s.customers})::INTEGER AS customer_id, "
        f"CASE WHEN r(k, 'about') < 0.7 THEN 1 + floor(r(k, 'torder') * {s.orders})::INTEGER END AS order_id, "
        "TIMESTAMP '"
        + FIRST_DAY
        + "' + to_seconds(floor(r(k, 'opened') * 730 * 86400)::BIGINT) AS opened_at, "
        "pick(['Low', 'Normal', 'Normal', 'High', 'Urgent'], k, 'prio') AS priority "
        f"FROM range(1, {s.orders * s.tickets_per_100_orders // 100 + 1}) t(k)) "
        "SELECT k AS ticket_id, customer_id, order_id, opened_at, "
        "CASE WHEN opened_at > TIMESTAMP '" + LAST_DAY + "' - INTERVAL 14 DAY AND r(k, 'open') < 0.6 "
        "THEN NULL ELSE opened_at + to_seconds(floor(600 + pow(r(k, 'took'), 2) * 6 * 86400)::BIGINT) "
        "END AS closed_at, priority, "
        "CASE WHEN closed_at IS NULL THEN pick(['New', 'Open', 'Waiting on customer'], k, 'st') "
        "ELSE pick(['Resolved', 'Resolved', 'Closed'], k, 'st') END AS status, "
        "pick(['Email', 'Chat', 'Phone', 'Web form'], k, 'tch') AS channel, "
        f"pick({_SUBJECTS}, k, 'subj') AS subject, "
        f"CASE WHEN r(k, 'assigned') < 0.12 THEN NULL ELSE {director + n_regions + 1} "
        f"+ floor(r(k, 'agent') * {n_support})::INTEGER END AS assigned_employee_id, "
        "CASE priority WHEN 'Urgent' THEN 4 WHEN 'High' THEN 8 WHEN 'Normal' THEN 24 ELSE 72 END "
        "AS sla_hours, "
        "floor(5 + pow(r(k, 'first'), 2.5) * 2880)::INTEGER AS first_response_minutes FROM t",
        # a few orders sent twice (the same row again): last, so the tables above see each order once
        "CREATE OR REPLACE TEMP TABLE dq_twice AS SELECT order_id FROM orders "
        f"WHERE order_id NOT IN (SELECT order_id FROM dq_late) ORDER BY r(order_id, 'twice') LIMIT {p}",
        "INSERT INTO orders SELECT * FROM orders WHERE order_id IN (SELECT order_id FROM dq_twice)",
        "CREATE OR REPLACE TABLE data_quality_issues AS "
        "SELECT row_number() OVER (ORDER BY table_name, key_value) AS issue_id, * FROM ("
        "SELECT 'orders' AS table_name, 'order_id' AS key_column, order_id::VARCHAR AS key_value, "
        "'duplicate row' AS problem, 'The same order was sent twice: two identical rows.' AS detail "
        "FROM dq_twice UNION ALL "
        "SELECT 'orders', 'order_id', order_id::VARCHAR, 'late-arriving row', "
        "'Loaded 42 days after it was placed (loaded_at against order_date).' FROM dq_late UNION ALL "
        "SELECT 'order_lines', 'order_line_id', order_line_id::VARCHAR, 'negative quantity', "
        "'A quantity below zero (and its line_total too) on a sale.' FROM dq_negative UNION ALL "
        "SELECT 'shipments', 'shipment_id', shipment_id::VARCHAR, 'delivered before shipped', "
        "'delivered_on is two days before shipped_on.' FROM dq_early UNION ALL "
        "SELECT 'customers', 'customer_id', i::VARCHAR, 'duplicate customer', "
        f"'The same person as customer ' || ((i - {s.customers}) * 7) || ': the same name and email.' "
        f"FROM range({s.customers + 1}, {s.customers + p + 1}) t(i))",
    ]


def generate(connection: duckdb.DuckDBPyConnection, scale: str = "small", seed: int = SEED) -> dict[str, int]:
    """Make every table in `connection` (replacing ones of the same names); returns each table's rows."""
    if scale not in SCALES:
        raise ValueError(f"No scale called {scale}: small, medium or large.")
    for statement in _sql(SCALES[scale], seed):
        connection.execute(statement)
    return {t: int(connection.execute(f"SELECT count(*) FROM {t}").fetchone()[0]) for t in TABLES}  # type: ignore[index]


def _outside_repository(out: Path) -> Path:
    out = out.expanduser().resolve()
    if out == REPOSITORY or REPOSITORY in out.parents:
        raise ValueError(f"Write the dataset outside the repository ({REPOSITORY}): pick another folder.")
    return out


def build(
    out: str | Path,
    scale: str = "small",
    seed: int = SEED,
    duckdb_file: bool = False,
    threads: int | None = None,
) -> Report:
    """Make the tables and write each as <out>/<table>.parquet (and, with duckdb_file, <out>/larkfield.duckdb
    holding them all). `out` is made when missing and must be outside the repository."""
    folder = _outside_repository(Path(out))
    folder.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    database = folder / "larkfield.duckdb"
    if duckdb_file and database.exists():
        database.unlink()
    connection = duckdb.connect(str(database) if duckdb_file else ":memory:")
    try:
        if threads:
            connection.execute(f"SET threads = {int(threads)}")
        report = Report(scale, int(seed), str(folder))
        report.rows = generate(connection, scale, seed)
        for table in TABLES:
            target = folder / f"{table}.parquet"
            order = ", ".join(KEYS[table])
            path = str(target).replace("'", "''")
            connection.execute(
                f"COPY (SELECT * FROM {table} ORDER BY {order}) TO '{path}' (FORMAT parquet, COMPRESSION zstd)"
            )
            report.files.append(str(target))
        if duckdb_file:
            report.files.append(str(database))
    finally:
        connection.close()
    report.seconds = time.perf_counter() - started
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tools.testbed.large_company",
        description="Write Larkfield Goods, a made-up retail and wholesale business, as Parquet files.",
    )
    parser.add_argument("--scale", choices=sorted(SCALES), default="small")
    parser.add_argument("--out", required=True, help="the folder to write into (outside the repository)")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--duckdb", action="store_true", help="also write larkfield.duckdb with every table")
    args = parser.parse_args(argv)
    try:
        report = build(args.out, args.scale, args.seed, args.duckdb)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    width = max(len(t) for t in report.rows)
    for table, rows in report.rows.items():
        print(f"{table:<{width}}  {rows:>12,}")
    print(f"{args.scale} written to {report.out} in {report.seconds:.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
