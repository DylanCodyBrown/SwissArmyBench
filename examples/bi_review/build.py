"""Test app one: a BI review of a made-up company's monthly sales, built the way a user's agent builds it.

Every step is one of the agent's commands (swissarmybench/cli/commands.py, the MCP tools) against a running
Swiss Army Bench, so the build proves the golden rule: what the user can do, the agent can do. The data is
Larkfield Goods (tools/testbed/large_company.py, small scale): made up, every row from a seed.

    build(run, allow, data, folder) -> Built

`run(command, **arguments)` runs one command and gives back its JSON; `allow()` is a context manager during
which the user answers the app's questions (an export's Allow, a save that keeps the board's table cards'
rows): the agent never answers its own. `data` is
a folder Larkfield Goods was written to (Parquet files and larkfield.duckdb); `folder` the new project's.

What it makes, in the order a person would:
  project      New project (the BI type), Autosave on
  connections  a folder of Parquet files (its path a ${LARKFIELD_DIR} variable), the DuckDB file, a SQLite
               archive, a CSV file and a Python connection (sales targets); each tested and its tables
               listed; a colour; the queries' limits; one table's connection swapped (and undone, then again)
  grids        the tables opened, DuckDB SQL naming [Connection].table, every kind of step on customers,
               a profile, compare and tie-out, the Key Finder, relationships found and set, the ERD and a
               relationship set, exports as CSV, Parquet and Excel
  analyze      every analysis contract on the columns it fits, Make it fit on a text date, a dashboard
  workbench    data.ipynb (SQL cells, a Python cell, an HTML cell, a uses line with an @cell link), a
               script in the same Python session, lineage, Export data.py, both as one automation
  structures   a JSON and a TOML file (and YAML when PyYAML is here): steps, Open as grid, Save as
  deliverable  an Excel workbook from the project by sab_excel (a design with a table and a total row)
  read back    ARCHITECTURE.md, the change log, the statistics, the Environment's tabs, Power BI's plan
  and again    Save, close, open again (every table back with its steps), Copy project to

Laid out top to bottom: the example's own files, the notebook's cells, then one function a part, build().
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb

HERE = Path(__file__).resolve().parent
Run = Callable[..., Any]
Allow = Callable[[], AbstractContextManager[None]]

# ===== the notebook's cells (data.ipynb) =====

CELLS: list[dict[str, Any]] = [
    {
        "kind": "markdown",
        "source": "# Larkfield Goods: monthly sales review\nMade-up data (Larkfield Goods, small).",
    },
    {
        "kind": "sql",
        "connection": "Larkfield Warehouse -> region_orders",
        "source": "SELECT s.region_id, count(*) AS orders\nFROM orders AS o JOIN stores AS s ON s.store_id = "
        "o.store_id\nGROUP BY s.region_id ORDER BY s.region_id",
    },
    {
        "kind": "sql",
        "connection": "-> monthly",
        "source": "SELECT region, month, revenue FROM monthly_sales ORDER BY region, month",
    },
    {
        "kind": "code",
        "source": "# uses monthly @cell3\n"
        "by_region = monthly.groupby('region', as_index=False)['revenue'].sum()\n"
        "best_region = by_region.sort_values('revenue').iloc[-1]['region']\n"
        "total_revenue = round(float(by_region['revenue'].sum()), 2)\n"
        "by_region",
    },
    {
        "kind": "html",
        "source": "<h2>Best region: {{ best_region }}</h2>\n"
        "<p>Revenue over two years: {{ total_revenue }}</p>\n{{ by_region }}",
        "height": 320,
    },
]

# The monthly sales by region, as DuckDB SQL over three connections' tables (the "+" tab).
MONTHLY = """SELECT r.region_name AS region, date_trunc('month', o.order_date) AS month,
       count(DISTINCT o.order_id) AS orders, round(sum(l.line_total), 2) AS revenue
FROM [Larkfield Warehouse].orders AS o
JOIN [Larkfield Files]."order_lines.parquet" AS l ON l.order_id = o.order_id
JOIN [Larkfield Warehouse].stores AS s ON s.store_id = o.store_id
JOIN [Larkfield Warehouse].regions AS r ON r.region_id = s.region_id
GROUP BY ALL ORDER BY region, month"""
# The same, in the warehouse's own SQL on the warehouse (the tie-out's other side).
MONTHLY_WAREHOUSE = """SELECT r.region_name AS region, date_trunc('month', o.order_date) AS month,
       count(DISTINCT o.order_id) AS orders, round(sum(l.line_total), 2) AS revenue
FROM orders AS o JOIN order_lines AS l ON l.order_id = o.order_id
JOIN stores AS s ON s.store_id = o.store_id JOIN regions AS r ON r.region_id = s.region_id
GROUP BY ALL ORDER BY region, month"""
# One row a sold line, with what Analyze reads: a date, amounts, categories, a yes/no outcome.
SALES_LINES = """SELECT l.order_line_id, o.order_date, date_trunc('month', o.order_date) AS month, o.channel,
       o.status, c.segment, r.region_name AS region, p.category_id, l.quantity, l.unit_price, l.discount_pct,
       l.line_total, CASE WHEN rt.order_line_id IS NULL THEN 'no' ELSE 'yes' END AS returned
FROM [Larkfield Files]."order_lines.parquet" AS l
JOIN [Larkfield Warehouse].orders AS o ON o.order_id = l.order_id
JOIN [Larkfield Warehouse].customers AS c ON c.customer_id = o.customer_id
JOIN [Larkfield Warehouse].stores AS s ON s.store_id = o.store_id
JOIN [Larkfield Warehouse].regions AS r ON r.region_id = s.region_id
JOIN [Larkfield Warehouse].products AS p ON p.product_id = l.product_id
LEFT JOIN (SELECT DISTINCT order_line_id FROM [Larkfield Warehouse].returns) AS rt
  ON rt.order_line_id = l.order_line_id"""

# The Python connection: monthly sales targets per region (made up from its TARGET_GROWTH variable).
TARGETS_CONNECT = (
    'import os\n\nconn = {"regions": 8, "growth": float(os.environ.get("TARGET_GROWTH", "0.05"))}\n'
)
TARGETS_TABLES = (
    '[{"table": "monthly_targets", "column": c, "type": t}\n'
    ' for c, t in (("region_id", "BIGINT"), ("month", "DATE"), ("target", "DOUBLE"))]\n'
)
TARGETS_READ = """import datetime as _dt

rows = []
for region in range(1, conn["regions"] + 1):
    for m in range(24):
        year, month = 2024 + (10 + m) // 12, (10 + m) % 12 + 1
        rows.append({"region_id": region, "month": _dt.date(year, month, 1),
                     "target": round(4000 * (1 + conn["growth"]) ** (m / 12) * (1 + region / 10), 2)})
rows if limit is None else rows[:limit]
"""

# Every kind of step (steps_kinds), on the customers table read from the archive.
STEPS: list[tuple[str, dict[str, Any]]] = [
    ("transform", {"fn": "trim_both", "columns": ["customer_name"]}),
    ("transform", {"fn": "lower", "columns": ["email"]}),
    ("rename", {"mapping": {"loyalty_tier": "tier"}}),
    ("filter", {"column": "segment", "op": "not_blank"}),
    ("sql", {"sql": "SELECT *, CAST(signup_date AS DATE) AS signup FROM grid"}),
    ("bucket", {"column": "signup", "as": "signup_month", "mode": "date", "unit": "month"}),
    (
        "categorize",
        {
            "column": "tier",
            "as": "tier_band",
            "unmatched": "Other",
            "rules": [{"type": "in", "label": "Top", "values": ["Gold"]}],
        },
    ),
    ("sort", {"keys": [["signup", "desc"], ["customer_id", "asc"]]}),
    (
        "columns",
        {
            "keep": [
                "customer_id",
                "customer_name",
                "segment",
                "region_id",
                "email",
                "tier",
                "tier_band",
                "signup",
                "signup_month",
            ]
        },
    ),
    ("distinct", {}),
    ("limit", {"n": 400}),
]
WAREHOUSE_TABLES = ("orders", "products", "customers", "stores", "regions", "categories", "returns")
KEYS = {
    "regions": ["region_id"],
    "stores": ["store_id"],
    "customers": ["customer_id"],
    "products": ["product_id"],
    "categories": ["category_id"],
    "order_lines": ["order_line_id"],
}


@dataclass
class Built:
    """What the build made and read back: the test checks each."""

    folder: Path
    grids: dict[str, str] = field(default_factory=dict)  # each table's first grid
    facts: dict[str, Any] = field(default_factory=dict)


def _type(run: Run, kind: str) -> dict[str, Any]:
    found: dict[str, Any] = next(t for t in run("connections_types")["types"] if t["id"] == kind)
    return found


def _filled(run: Run, kind: str, value: str) -> tuple[str, dict[str, Any]]:
    """A connection type's code with its one setting filled (as the form's box does)."""
    made = _type(run, kind)
    setting = run("blades_inspect", code=made["code"])["settings"][0]["id"]
    return str(run("blades_fill", code=made["code"], values={setting: value})["code"]), made


def archive(data: Path) -> Path:
    """A SQLite copy of three tables (the archive; dates as text, as an old system keeps them)."""
    path = data / "archive.sqlite"
    path.unlink(missing_ok=True)
    db, own = sqlite3.connect(path), duckdb.connect()  # a DuckDB of its own (the app locks the default one)
    try:
        for table in ("customers", "products", "regions"):
            read = own.execute(f"SELECT * FROM '{data / table}.parquet' ORDER BY 1")  # noqa: S608 (made-up)
            names = [d[0] for d in read.description]
            db.execute(f"CREATE TABLE {table} ({', '.join(names)})")
            rows = [
                tuple(v.isoformat() if hasattr(v, "isoformat") else v for v in r) for r in read.fetchall()
            ]
            db.executemany(f"INSERT INTO {table} VALUES ({', '.join('?' * len(names))})", rows)  # noqa: S608
        db.commit()
    finally:
        db.close()
        own.close()
    return path


def connections(run: Run, data: Path, built: Built) -> None:
    run("variables_set", name="LARKFIELD_DIR", value=str(data), local=True)
    run("variables_set", name="TARGET_GROWTH", value="0.05")
    folder = _type(run, "folder")
    setting = run("blades_inspect", code=folder["code"])["settings"][0]["id"]
    # ${LARKFIELD_DIR} in the folder's box: written into its code as os.environ["LARKFIELD_DIR"].
    code = run("blades_fill", code=folder["code"], values={setting: "${LARKFIELD_DIR}"})["code"]
    built.facts["files_code"] = code
    tested = {
        "Larkfield Files": run(
            "connections_test", name="Larkfield Files", kind="other", template="folder", code=code
        )
    }
    run(
        "connections_create",
        name="Larkfield Files",
        kind="other",
        template="folder",
        code=code,
        catalog=folder["catalog"],
        description="Larkfield Goods' monthly extracts",
    )
    for name, kind, path in (
        ("Larkfield Warehouse", "duckdb", data / "larkfield.duckdb"),
        ("Larkfield Archive", "sqlite", archive(data)),
    ):
        code, made = _filled(run, kind, str(path))
        tested[name] = run("connections_test", name=name, kind="sql", template=kind, code=code)
        run(
            "connections_create",
            name=name,
            kind="sql",
            template=kind,
            dialect=kind,
            code=code,
            catalog=made["catalog"],
        )
    stores = f"COPY (SELECT * FROM '{data / 'stores.parquet'}') TO '{data / 'stores.csv'}' (HEADER)"  # noqa: S608 (made-up)
    with duckdb.connect() as own:
        own.execute(stores)
    code, made = _filled(run, "csv", str(data / "stores.csv"))
    run(
        "connections_create",
        name="Store List",
        kind="other",
        template="csv",
        code=code,
        catalog=made["catalog"],
    )
    targets = {
        "connect": TARGETS_CONNECT,
        "tables": TARGETS_TABLES,
        "read": TARGETS_READ,
        "variables": [{"name": "TARGET_GROWTH", "from": "value", "value": "0.05"}],
    }
    tested["Targets"] = run("connections_python_save", name="Targets", test=True, **targets)
    run("connections_python_save", name="Targets", description="Monthly sales targets", **targets)
    tested["Targets saved"] = run("connections_test", name="Targets")
    built.facts["tested"] = tested
    built.facts["tables"] = {
        name: [t["sql"] for g in run("connections_tables", name=name)["groups"] for t in g["tables"]]
        for name in ("Larkfield Files", "Larkfield Warehouse", "Larkfield Archive", "Store List", "Targets")
    }
    built.facts["colour"] = run("connections_colours", name="Larkfield Warehouse", colour="#c2410c")
    built.facts["limits"] = run(
        "connections_set_limits", name="Larkfield Warehouse", total=4, agent=2, wait=60
    )


def tables(run: Run, built: Built) -> None:
    opened = run("connections_open_table", name="Larkfield Files", table="order_lines.parquet")
    built.grids["order_lines"] = opened["grid"]
    for table in WAREHOUSE_TABLES:
        built.grids[table] = run(
            "connections_open_table", name="Larkfield Warehouse", table=table, schema="main"
        )["grid"]
    built.grids["monthly_targets"] = run("connections_open_table", name="Targets", table="monthly_targets")[
        "grid"
    ]
    made = run("tabs_new_query", name="monthly_sales", sql=MONTHLY)
    built.grids["monthly_sales"] = made["grid"]
    built.facts["monthly_reads"] = made["connection_reads"]
    built.grids["monthly_sales_wh"] = run(
        "tabs_new_connection_query",
        name="monthly_sales_wh",
        connection="Larkfield Warehouse",
        sql=MONTHLY_WAREHOUSE,
    )["grid"]
    built.grids["sales_lines"] = run("tabs_new_query", name="sales_lines", sql=SALES_LINES)["grid"]
    built.facts["sql_reads"] = run("connections_sql_reads")["reads"]
    built.facts["slots"] = run("connections_slots")["connections"]
    built.facts["queries"] = run("connections_queries", connection="Larkfield Warehouse")
    # The customers table moves to the archive: its steps (none yet) kept; undone; moved again.
    swap = {"first": run("table_swap_connection", table="customers", to="Larkfield Archive")}
    swap["undo"] = run("table_swap_undo", table="customers")
    swap["back"] = run("table_connection", table="customers")
    swap["again"] = run("table_swap_connection", table="customers", to="Larkfield Archive")
    swap["now"] = run("table_connection", table="customers")
    swap["order_lines"] = run("table_connection", table="order_lines")
    built.facts["swap"] = swap


def grids(run: Run, built: Built) -> None:
    customers = built.grids["customers"]
    bad = dict(
        STEPS[6][1], rules=[{"label": "Top", "rule": {"type": "in"}}]
    )  # the shape a first try got wrong
    for kind, params in STEPS:
        run("steps_add", grid=customers, kind=kind, params=bad if kind == "categorize" else params)
    built.facts["step_error"] = run("tabs_get", grid=customers)["step_error"]
    run("steps_edit", grid=customers, index=6, params=STEPS[6][1])  # the step's Edit, the rule put right
    run("steps_undo", grid=customers)
    run("steps_redo", grid=customers)
    built.facts["customers"] = run("tabs_get", grid=customers)
    built.facts["profile"] = run("table_profile", grid=customers)
    built.facts["column_profile"] = run("column_profile", grid=customers, column="tier_band")
    by_product = run("tabs_create_grid", dataset="order_lines")["grid"]  # a second view: lines by product
    built.facts["by_product"] = run(
        "steps_add",
        grid=by_product,
        kind="group_by",
        params={
            "keys": ["product_id"],
            "aggregates": [
                {"fn": "sum", "column": "line_total", "as": "revenue"},
                {"fn": "count_rows", "as": "lines"},
            ],
        },
    )
    compare = run(
        "compare_create",
        left=built.grids["monthly_sales"],
        right=built.grids["monthly_sales_wh"],
        keys=[["region", "region"], ["month", "month"]],
    )
    built.facts["compare"] = compare
    built.facts["tie_out_choices"] = run("compare_tie_out", compare=compare["compare"])
    built.facts["tie_out"] = run(
        "compare_tie_out", compare=compare["compare"], group=["region"], measures=["revenue", "orders"]
    )
    built.facts["key_finder"] = run("key_finder_run", grid=built.grids["orders"])
    named = ["orders", "order_lines", "customers", "stores", "regions", "products", "categories"]
    found = run("relationships_find", tables=named)["suggestions"]
    built.facts["found"] = found
    joins = [
        {k: s[k] for k in ("from", "from_columns", "to", "to_columns", "kind")}
        for s in found
        if s["confidence"] >= 0.9
    ]
    # orders.order_id is not unique (an order sent twice, on purpose): the finder leaves it; a person knows.
    joins.append(
        {
            "from": "order_lines",
            "from_columns": ["order_id"],
            "to": "orders",
            "to_columns": ["order_id"],
            "kind": "many-to-one",
        }
    )
    model = {
        "name": "larkfield_sales",
        "description": "Larkfield Goods' sales model",
        "tables": {t: {"primary_key": k} for t, k in KEYS.items()},
        "relationships": joins,
    }
    run("relationships_set", model=model, replace=True)
    built.facts["erd"] = run("erd_text")
    built.facts["erd_card"] = run("erd_draw", grid=built.grids["orders"], title="Larkfield sales model")
    built.facts["set"] = run(
        "relationships_save_set", name="Larkfield sales", description="How the sales join"
    )
    built.facts["sets"] = run("relationships_library")["models"]


def exports(run: Run, allow: Allow, built: Built) -> None:
    saved = {}
    for fmt in ("csv", "parquet", "xlsx"):
        with allow():  # an agent's export waits for the user's click
            saved[fmt] = run(
                "table_export",
                grid=built.grids["monthly_sales"],
                format=fmt,
                file="monthly_sales",
                overwrite=True,
            )["saved"]
    built.facts["exports"] = saved


def analyze(run: Run, built: Built) -> None:
    ranked = run("analyze_check", table="sales_lines")["ranked"]
    runs: dict[str, Any] = {}
    for item in ranked:
        runs[item["analysis"]] = run("analyze_run", analysis=item["analysis"], table="sales_lines")
    for analysis in ("profile", "check"):
        runs[analysis] = run("analyze_run", analysis=analysis, table="sales_lines")
    built.facts["ranked"] = ranked
    built.facts["runs"] = runs
    # Make it fit: the archive keeps sign-up dates as text; the fix reads them as dates (a grid step).
    archive_grid = run("tabs_create_grid", dataset="customers")["grid"]
    check = run("analyze_check", table=archive_grid, analysis="time_series")
    fix = next(f for f in check["fixes"] if f["kind"] == "text_to_date")
    built.facts["fit_before"] = check
    built.facts["fit"] = run("analyze_fix", analysis="time_series", table=archive_grid, fixes=[fix["id"]])
    built.facts["fitted"] = run(
        "analyze_run", analysis="time_series", table=archive_grid, columns={"date": fix["column"]}
    )
    built.facts["contracts"] = run("analyze_contracts")
    built.facts["dashboard"] = run("analyze_dashboard", action="save", name="monthly_sales_review")
    built.facts["dashboards"] = run("analyze_dashboards")


def workbench(run: Run, built: Built) -> None:
    folder = built.folder
    data = str(folder / "data.ipynb")
    opened = run("workbench_open", path=data)
    run("workbench_save", path=data, cells=CELLS, modified=opened["modified"], next_cell=opened["next_cell"])
    built.facts["notebook"] = run("workbench_open", path=data)
    for name in ("monthly_review.py", "review_workbook.py"):
        (folder / "scripts").mkdir(exist_ok=True)
        text = (HERE / "scripts" / name).read_text(encoding="utf-8")
        run("workbench_save", path=str(folder / "scripts" / name), text=text)
    kernel = run("workbench_kernel_start", path=data)
    built.facts["kernel"] = kernel
    built.facts["ran"] = run("workbench_run_notebook", path=data, kernel=kernel["kernel"])
    script = str(folder / "scripts" / "monthly_review.py")
    other = run("workbench_kernel_start", path=script)
    built.facts["same_session"] = other["kernel"] == kernel["kernel"]
    built.facts["script_ran"] = run(
        "workbench_run", kernel=other["kernel"], kind="file", path=script, document=script
    )
    # The script's headline and the notebook's best region in one Python: one session for the project.
    built.facts["shared"] = run(
        "workbench_run",
        kernel=kernel["kernel"],
        document=data,
        code="print(headline['orders'], best_region, total_revenue)",
    )
    built.facts["lineage"] = run("workbench_lineage", document=data, cell=5)
    built.facts["table_cells"] = run("workbench_table_cells")["tables"]
    values = built.facts["ran"]["results"][-1]["outputs"][0]["values"]  # as the HTML cell's run gave them
    built.facts["html"] = run("workbench_html_fill", html=CELLS[4]["source"], values=values)
    built.facts["data_py"] = run("project_export_data", folder=str(folder), replace=True)
    built.facts["exported"] = {
        "data": run("workbench_export_script", path=data, check=True),
        "script": run("workbench_export_script", path=script),
    }
    book = str(folder / "scripts" / "review_workbook.py")
    built.facts["workbook_ran"] = run(
        "workbench_run", kernel=kernel["kernel"], kind="file", path=book, document=book
    )


def structures(run: Run, built: Built, yaml: bool) -> None:
    inputs = built.folder / "inputs"
    shutil.copytree(HERE / "inputs", inputs, dirs_exist_ok=True)
    plan = run("structures_open", path=str(inputs / "review_plan.json"))
    run(
        "structures_step_add",
        structure=plan["id"],
        step={"op": "filter", "path": "$.regions", "field": "status", "value": "open"},
    )
    run(
        "structures_step_add",
        structure=plan["id"],
        step={"op": "rename", "path": "$.regions[*]", "key": "target", "to": "monthly_target"},
    )
    built.facts["plan_grid"] = run(
        "structures_open_as_grid", structure=plan["id"], path="$.regions", name="review_regions"
    )
    built.facts["plan_saved"] = run("structures_save", structure=plan["id"], name="review_plan_open")
    toml = run("structures_open", path=str(inputs / "thresholds.toml"))
    run(
        "structures_step_add",
        structure=toml["id"],
        step={"op": "sort", "path": "$.thresholds", "field": "warn", "descending": True},
    )
    built.facts["thresholds_grid"] = run(
        "structures_open_as_grid", structure=toml["id"], path="$.thresholds", name="thresholds"
    )
    built.facts["toml_saved"] = run("structures_save", structure=toml["id"], name="thresholds", format="json")
    if yaml:
        built.facts["yaml"] = run("structures_open", path=str(inputs / "thresholds.yaml"))
    built.facts["structures"] = run("structures_list")


def read_back(run: Run, built: Built, powerbi: bool) -> None:
    built.facts["outline"] = run("project_outline", write=True)
    built.facts["changes"] = run("changes", action="search", n=200)["changes"]
    built.facts["stats"] = run("stats")
    built.facts["stats_connection"] = run("stats", action="connection", name="Larkfield Warehouse")
    environment: dict[str, Any] = {"list": run("environment", action="list")}
    library = next(r["name"] for r in records(environment["list"]) if r.get("kind") == "library")
    for kind, name in (
        ("table", "monthly_sales"),
        ("variable", "best_region"),
        ("setting", "LARKFIELD_DIR"),
        ("structure", "review_plan_open"),
        ("library", library),
    ):
        environment[kind] = run("environment", action="show", args={"kind": kind, "name": name})
    environment["libraries"] = run("environment", action="libraries")
    environment["uses"] = run("variables_uses", name="LARKFIELD_DIR")
    built.facts["environment"] = environment
    if powerbi:
        built.facts["powerbi"] = run("powerbi_export", dry_run=True)


def again(run: Run, allow: Allow, built: Built, copy_to: Path) -> None:
    run("project_autosave", on=False)
    # The two tables opened from structures keep their rows (they are read again from no source); the board's
    # table cards hold rows too: the agent's save asks the user first.
    with allow():
        built.facts["saved"] = run("project_save", keep_rows={"review_regions": True, "thresholds": True})
    run("project_autosave", on=True)
    with allow():
        built.facts["closed"] = run("project_close")
    built.facts["reopened"] = run("project_open", path=str(built.folder))
    built.facts["reopened_tabs"] = run("tabs_list")["grids"]
    with allow():
        built.facts["copied"] = run("project_copy", path=str(copy_to))


def build(
    run: Run, allow: Allow, data: Path, folder: Path, yaml: bool = False, powerbi: bool = False
) -> Built:
    """The whole app, part by part (see the module's words), into `folder`; what it made and read back."""
    built = Built(folder)
    built.facts["project"] = run("project_new", path=str(folder), type="bi")
    connections(run, data, built)
    tables(run, built)
    grids(run, built)
    exports(run, allow, built)
    analyze(run, built)
    workbench(run, built)
    structures(run, built, yaml)
    read_back(run, built, powerbi)
    again(run, allow, built, folder.parent / f"{folder.name}_copy")
    return built


def records(found: Any) -> Iterator[dict[str, Any]]:
    """Each dict in an answer, at any depth (for the test's searches)."""
    if isinstance(found, dict):
        yield found
        for value in found.values():
            yield from records(value)
    elif isinstance(found, list):
        for value in found:
            yield from records(value)


def text_of(found: Any) -> str:
    return json.dumps(found, default=str)
