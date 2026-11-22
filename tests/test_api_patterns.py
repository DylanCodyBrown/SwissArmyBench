"""The endpoint wizard's patterns (the owner, 2026-11-21: "a handful of api types that are universal to the
sandbox" / "one uniform wizard" / "Steps are different depending on the API"):

  as data     the nine patterns, each with its own steps and its widget pairing; an extension adds one
  ranked      a table's shape ranks them, each with one sentence why
  one style   every pattern's code is the adapter's connection(name).read / .query / .write, for every source
  it runs     each pattern scaffolded through the app, hosted, and called against the sandbox: DuckDB, a
              table mocked as a SQL Server connection (its own SQL through the mock), and the parts a source
              cannot fold done by DuckDB over the stream, said in the endpoint's data words
  the agent   api(plan) and api(scaffold) with a dry run that writes nothing
  exports     all nine exported for the three targets and run against the real connection

Made-up data only."""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from swissarmybench.domain import api_patterns as patterns
from swissarmybench.domain import api_scaffold as scaffold
from swissarmybench.domain import local_api as rules
from swissarmybench.server import api_runtime
from tests.conftest import AUTH, make_client
from tests.fake_keyring import memory_keyring
from tests.test_api_export import AZURE_STANDIN, FASTAPI_STANDIN, KEYRING_SECRET, _run, ok
from tests.test_local_api import _ask, live  # noqa: F401

ORDERS = (
    {"name": "order_id", "type": "BIGINT", "key": True},
    {"name": "customer", "type": "VARCHAR"},
    {"name": "region", "type": "VARCHAR"},
    {"name": "status", "type": "VARCHAR"},
    {"name": "order_date", "type": "DATE"},
    {"name": "amount", "type": "DOUBLE"},
)
LEDGER = (
    {"name": "order_id", "type": "BIGINT"},
    {"name": "amount", "type": "DOUBLE"},
    {"name": "posted", "type": "DATE"},
)
FORMS = (
    {"name": "form_id", "type": "BIGINT"},
    {"name": "version", "type": "INTEGER"},
    {"name": "title", "type": "VARCHAR"},
)
ORDERS_CSV = (
    "order_id,customer,region,status,order_date,amount\n"
    "1,Ada Fenn,North,open,2026-01-05,120.5\n"
    "2,Bo Larch,East,open,2026-01-20,80.0\n"
    "3,Cy Moss,North,closed,2026-02-03,40.0\n"
    "4,Di Reed,South,open,2026-02-14,200.0\n"
    "5,Ed Vane,East,closed,2026-03-01,60.0\n"
)
LEDGER_CSV = (
    "order_id,amount,posted\n"
    "1,120.5,2026-01-06\n"
    "2,85.0,2026-01-21\n"
    "3,40.0,2026-02-04\n"
    "4,200.0,2026-02-15\n"
    "9,10.0,2026-03-09\n"
)
FORMS_CSV = "form_id,version,title\n1,1,Intake\n1,2,Intake two\n2,1,Exit\n"
STYLES = (
    scaffold.Source("duckdb", "Sandbox"),
    scaffold.Source("database", "Warehouse", "sqlserver", "dbo"),
    scaffold.Source("database", "Shop", "postgres", "public"),
    scaffold.Source("database", "Ledger", "oracle"),
    scaffold.Source("database", "Books", "mysql"),
    scaffold.Source("database", "Lake", "trino"),
    scaffold.Source("database", "Local", "sqlite"),
    scaffold.Source("dataverse", "Sales CRM", "dataverse"),
    scaffold.Source("sharepoint", "Team site"),
)
# Each pattern with the fields a test gives it (the rest: its defaults from the table's shape).
CASES: tuple[tuple[str, str, dict[str, Any], str | None], ...] = (
    ("table", "orders", {}, None),
    ("choices", "orders", {"value": "region", "label": "region"}, None),
    ("search", "orders", {}, None),
    ("summary", "orders", {}, None),
    ("summary", "orders", {"group": [], "date": "order_date", "period": "month"}, None),
    ("bulk", "orders", {}, None),
    ("action", "orders", {"only": "status", "only_value": "open"}, None),
    ("versions", "forms", {}, None),
    ("reconcile", "orders", {}, "ledger"),
    ("export", "orders", {}, None),
    ("export", "orders", {"format": "xlsx", "columns": ["order_id", "customer", "amount"]}, None),
)


def _targets(source: scaffold.Source) -> dict[str, patterns.Target]:
    return {
        "orders": patterns.Target("orders", ORDERS, source, 5000),
        "ledger": patterns.Target("ledger", LEDGER, source, 5000),
        "forms": patterns.Target("forms", FORMS, source, 3),
    }


def _all(source: scaffold.Source) -> str:
    """API.py with every case's block appended, as the service appends them."""
    registry = patterns.Registry()
    tables = _targets(source)
    text = rules.scaffold("shop")
    for wanted, table, fields, other in CASES:
        api = rules.parse(text)
        names = [e.name for e in api.endpoints] + list(api.models)
        taken = patterns.Taken(tuple(names), tuple(e.path for e in api.endpoints))
        made = registry.make(wanted, tables[table], fields, taken, tables[other] if other else None)
        text, needs = scaffold.with_imports(text, scaffold.imports_missing(text, made.text))
        text = text.rstrip("\n") + "\n" + ("\n" + needs if needs else "") + made.text
    return text


# ===== as data =====


def test_the_nine_patterns_are_data_with_their_own_steps_and_widgets() -> None:
    registry = patterns.Registry()
    listed = {p["id"]: p for p in registry.listed()}
    assert list(listed) == [
        "table", "choices", "search", "summary", "bulk", "action", "versions", "reconcile", "export",
    ]  # fmt: skip
    # Steps are each pattern's own (the owner's correction), never five fixed ones.
    steps = {name: [s["id"] for s in p["steps"]] for name, p in listed.items()}
    assert steps["table"] == ["key"]
    assert steps["summary"] == ["group", "totals", "date", "period"]
    assert steps["reconcile"] == ["other", "key", "compare"] and listed["reconcile"]["tables"] == 2
    assert steps["action"] == ["name", "key", "sets", "only", "only_value"]
    assert len({tuple(s) for s in steps.values()}) == 9
    for p in listed.values():
        assert p["question"].endswith(".") and p["label"]
        for step in p["steps"]:
            assert step["kind"] in ("column", "columns", "choice", "text", "table", "totals", "sets"), step
    # Each names its widget pairing (Export has none: a download is the browser's own).
    assert [w["widget"] for w in listed["table"]["widgets"]] == ["api_table", "api_form"]
    assert {w["port"] for w in listed["choices"]["widgets"]} == {"options_table"}
    assert all(p["widgets"] for name, p in listed.items() if name != "export")


def test_an_extension_adds_its_own_pattern() -> None:
    def make(target: patterns.Target, fields: Any, taken: patterns.Taken, other: Any) -> patterns.Made:
        return patterns.Made(f"\n\n# pattern: ping of {target.name}\n", [])

    raw = {
        "id": "ping",
        "label": "Ping",
        "question": "Says the table is there.",
        "steps": [{"id": "word", "label": "Its word", "kind": "text"}],
        "widgets": [{"widget": "api_metric", "role": "ping"}],
        "make": make,
        "roles": ["ping"],
    }
    registry = patterns.Registry()
    registry.add(patterns.from_extension(raw, "made_up_extension"))
    assert registry.listed()[-1]["extension"] == "made_up_extension"
    assert "pattern: ping of orders" in registry.make("ping", _targets(STYLES[0])["orders"]).text
    assert registry.pairings("ping", "ping_orders")[0]["widget"] == "api_metric"
    assert "ping" not in patterns.Registry().patterns  # another registry keeps the base's nine
    with pytest.raises(ValueError, match="needs an id and a make"):
        patterns.from_extension({"id": "x"}, "made_up_extension")
    with pytest.raises(scaffold.ScaffoldError, match="The pattern is one of: table, choices"):
        registry.get("nope")


# ===== ranked by the table's shape =====


def test_a_tables_shape_ranks_the_patterns_with_one_sentence_why() -> None:
    registry = patterns.Registry()
    tables = _targets(STYLES[0])
    everything = list(tables.values())
    orders = registry.ranked(tables["orders"], everything)
    assert orders[0]["pattern"] == "table"
    assert orders[0]["why"] == "orders has a key (order_id): list, get, create, update and delete by it."
    by = {r["pattern"]: r for r in orders}
    assert by["action"]["why"].startswith("orders has status:")
    assert by["reconcile"]["why"].startswith("orders and ledger share order_id and amount")
    assert not by["versions"]["fits"] and "no version number column" in by["versions"]["why"]
    assert orders[-1]["pattern"] == "versions"  # what does not fit is last, said why
    forms = registry.ranked(tables["forms"], everything)
    assert forms[0]["pattern"] == "versions" and forms[0]["why"].startswith("forms has version:")
    # A short list with a name is a dropdown's choices; alone in the sandbox, nothing to reconcile with.
    regions = patterns.Target("regions", ({"name": "code", "type": "VARCHAR", "key": True},
                                          {"name": "name", "type": "VARCHAR"}), rows=12)  # fmt: skip
    alone = registry.ranked(regions, [regions])
    assert alone[0]["pattern"] == "table" and alone[1]["pattern"] == "choices"
    assert alone[1]["why"] == "regions is a short list with name: the choices of a dropdown."
    assert not {r["pattern"]: r for r in alone}["reconcile"]["fits"]
    for row in orders + forms + alone:
        assert row["why"].endswith(".") and "\n" not in row["why"], row


def test_a_patterns_plan_offers_the_columns_that_fit_and_what_the_shape_suggests() -> None:
    registry = patterns.Registry()
    tables = _targets(STYLES[0])
    summary = {s["id"]: s for s in registry.planned("summary", tables["orders"])["steps"]}
    assert summary["date"]["options"] == ["order_date"]  # only its dates
    assert summary["group"]["value"] == ["region"]
    assert summary["totals"]["value"] == [{"fn": "sum", "column": "amount"}, {"fn": "count", "column": ""}]
    given = registry.planned("summary", tables["orders"], {"group": ["status"]})
    assert given["fields"]["group"] == ["status"]  # what was given is kept
    versions = registry.planned("versions", tables["forms"])
    assert versions["fields"] == {"of": "form_id", "version": "version"}
    assert {s["id"]: s for s in versions["steps"]}["version"]["options"] == [
        "form_id",
        "version",
    ]  # whole numbers only
    both = registry.planned("reconcile", tables["orders"], None, tables["ledger"])
    steps = {s["id"]: s for s in both["steps"]}
    assert steps["other"]["value"] == "ledger" and steps["key"]["options"] == ["order_id", "amount"]
    assert both["fields"] == {"key": ["order_id"], "compare": ["amount"]}
    assert patterns.partner(tables["orders"], list(tables.values())) == tables["ledger"]


# ===== one style, every source =====


@pytest.mark.parametrize("source", STYLES, ids=lambda s: s.dialect if s.kind == "database" else s.kind)
def test_every_pattern_compiles_reads_and_is_marked_in_every_source_style(source: scaffold.Source) -> None:
    text = _all(source)
    compile(text, "API.py", "exec")
    api = rules.parse(text)
    assert api.problems == []
    by = {e.name: e for e in api.endpoints}
    assert len(by) == 18
    # One style: the adapter's calls on connection(name); never a cursor, a driver or a per-source client.
    assert "cursor" not in text and ".execute(" not in text and "read_arrow" not in text
    assert all(e.connections == [source.connection] for e in api.endpoints), [
        (e.name, e.connections) for e in api.endpoints
    ]
    # Each endpoint's pattern, from the block's one marker comment.
    made = {name: patterns.pattern_at(text, e.line) for name, e in by.items()}
    assert made["list_orders"] == ("table", "orders") and made["delete_orders"] == ("table", "orders")
    assert made["choices_orders_region"] == ("choices", "orders")
    assert made["summary_orders_by_month"] == ("summary", "orders")
    assert made["approve_orders"] == ("action", "orders")
    assert made["new_version_forms"] == ("versions", "forms")
    assert made["reconcile_orders_ledger_rows"] == ("reconcile", "orders and ledger")
    assert made["export_orders_xlsx"] == ("export", "orders")
    assert len(patterns.marked(text)) == len(CASES)
    # An endpoint written by hand below a banner of its own has no pattern.
    hand = (
        text + '\n\n# ===== my own =====\n\n\n@endpoint("GET", "/mine")\ndef mine() -> dict:\n    return {}\n'
    )
    assert patterns.pattern_at(hand, rules.parse(hand).endpoints[-1].line) == ("", "")
    # The first sentence of each docstring is whole (it is the endpoint's summary on the APIs page).
    assert all(e.summary.endswith(".") for e in api.endpoints), [e.summary for e in api.endpoints]
    # What the source can fold is one statement of its own SQL; what it cannot, DuckDB over the stream.
    has_sql = source.kind in ("duckdb", "database")
    assert by["summary_orders_by_month"].streams is (not has_sql)
    assert by["reconcile_orders_ledger"].streams is (not has_sql or source.dialect == "mysql")
    assert not by["summary_orders_by_region"].streams  # a plan: the adapter folds it
    if has_sql:
        assert by["summary_orders_by_month"].sql and by["summary_orders_by_month"].sql[0]["formatted"]


def test_a_summary_by_period_and_a_reconcile_are_written_in_the_sources_own_sql() -> None:
    tsql = _all(STYLES[1])
    assert "CAST(DATETRUNC(MONTH, [order_date]) AS DATE) AS [period]" in tsql
    assert "FROM [dbo].[orders] AS l" in tsql and "FULL OUTER JOIN [dbo].[ledger] AS r" in tsql
    assert "OFFSET {int(offset)} ROWS" in tsql and "FETCH FIRST {int(limit)} ROWS ONLY" in tsql
    postgres = _all(STYLES[2])
    assert 'CAST(DATE_TRUNC(\'MONTH\', "order_date") AS DATE) AS "period"' in postgres
    assert 'FROM "public"."orders" AS l' in postgres and "LIMIT {int(limit)}" in postgres
    # Dataverse's Web API has no SQL: the columns it needs are read with a plan, DuckDB does the rest.
    odata = _all(STYLES[7])
    assert (
        'connection("Sales CRM").read("orders", columns=["order_date", "amount"], filters=filters)' in odata
    )
    assert 'engine.register("left_rows", connection("Sales CRM").read("orders", columns=' in odata
    assert ".query(" not in odata
    # The page, the filters and the keys always go to the source in the read's plan.
    assert '"limit": limit, "offset": offset}' in tsql
    assert 'filters=[["order_id", "in", keys[start : start + 500]]]' in tsql


def test_a_pattern_refuses_what_it_cannot_make_in_one_sentence() -> None:
    registry = patterns.Registry()
    tables = _targets(STYLES[0])
    orders = tables["orders"]

    def refused(wanted: str, fields: dict[str, Any], other: patterns.Target | None = None) -> str:
        with pytest.raises(scaffold.ScaffoldError) as caught:
            registry.make(wanted, orders, fields, None, other)
        return str(caught.value)

    assert refused("summary", {"totals": [{"fn": "sum", "column": "region"}]}) == (
        "region is not a number: a sum takes a number column."
    )
    assert refused("summary", {"period": "month"}) == "Pick the date column."
    assert refused("versions", {}) == "Pick the version number."
    assert refused("action", {"sets": []}) == "Pick at least one column it sets, and the value."
    assert refused("action", {"sets": [{"column": "amount", "value": "lots"}]}) == (
        'amount holds numbers: "lots" is not one.'
    )
    assert refused("reconcile", {}) == "Reconcile compares two tables: pick the second one."
    assert refused("reconcile", {"key": ["customer"]}, tables["ledger"]) == (
        "ledger has no column customer to be compared (orders has it)."
    )
    assert (
        refused("export", {"format": "pdf"}) == "An export is a CSV file (csv) or an Excel workbook (xlsx)."
    )
    assert refused("search", {"text": "", "filters": []}) == (
        "Pick a column the text search looks in, or a column to filter by."
    )
    taken = patterns.Taken(("search_orders",), ("/orders/summary/region",))
    with pytest.raises(scaffold.ScaffoldError, match=r"API\.py has search_orders already"):
        registry.make("search", orders, {}, taken)
    with pytest.raises(scaffold.ScaffoldError, match=r"API\.py answers /orders/summary/region already"):
        registry.make("summary", orders, {}, taken)


# ===== the runtime the patterns stand on =====


def test_the_most_literal_path_answers_whichever_was_written_first() -> None:
    kept = list(api_runtime.ENDPOINTS)
    api_runtime.ENDPOINTS.clear()
    try:

        @api_runtime.endpoint("GET", "/orders/{key}")
        def one(key: int) -> dict[str, int]:
            return {"one": key}

        @api_runtime.endpoint("GET", "/orders/search")
        def search(q: str = "") -> dict[str, str]:
            return {"search": q}

        assert json.loads(api_runtime.handle("GET", "/orders/search", {"q": "a"})[2]) == {"search": "a"}
        assert json.loads(api_runtime.handle("GET", "/orders/7")[2]) == {"one": 7}
    finally:
        api_runtime.ENDPOINTS[:] = kept


def test_a_download_is_a_csv_file_or_an_excel_workbook_made_with_no_library() -> None:
    import datetime

    import pyarrow as pa

    rows = [
        {"order_id": 1, "customer": "Ada <Fenn> & co", "amount": 120.5, "day": datetime.date(2026, 1, 5)},
        {"order_id": 2, "customer": "Bo, Larch", "amount": None, "day": None},
    ]
    saved = api_runtime.download(rows, "orders.csv")
    assert saved.media.startswith("text/csv")
    assert saved.content.decode() == (
        'order_id,customer,amount,day\r\n1,Ada <Fenn> & co,120.5,2026-01-05\r\n2,"Bo, Larch",,\r\n'
    )
    status, headers, _ = api_runtime.answered(200, saved)
    assert status == 200 and headers["Content-Disposition"] == 'attachment; filename="orders.csv"'
    # An Arrow reader stays a stream (read a batch at a time); a table with no rows still has its header.
    reader = pa.Table.from_pylist(rows).to_reader()
    assert api_runtime.download(reader, "orders.csv").content == saved.content
    empty = pa.table({"a": pa.array([], pa.int64())})
    assert api_runtime.download(empty, "none.csv").content == b"a\r\n"
    book = api_runtime.download(pa.Table.from_pylist(rows), "orders.xlsx")
    assert book.media == api_runtime.XLSX
    with zipfile.ZipFile(io.BytesIO(book.content)) as parts:
        assert "xl/worksheets/sheet1.xml" in parts.namelist()
    openpyxl = pytest.importorskip("openpyxl")
    sheet = openpyxl.load_workbook(io.BytesIO(book.content)).active
    assert [[c.value for c in row] for row in sheet.iter_rows()] == [
        ["order_id", "customer", "amount", "day"],
        [1, "Ada <Fenn> & co", 120.5, "2026-01-05"],
        [2, "Bo, Larch", None, None],
    ]


# ===== it runs: scaffolded through the app, hosted, called against the sandbox =====


def _mock_as(folder: Path, table: str, client: dict[str, Any], schema: str = "") -> None:
    """A sandbox table as if read from a connection of that kind (its mock speaks that source)."""
    path = folder / ".sab" / "sandbox" / "sandbox.json"
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta["tables"][table]["client"] = client
    place = {"schema": schema} if schema else {}
    meta["tables"][table]["source"] = {
        "kind": "connection",
        "connection": client["connection"],
        "place": place,
    }
    path.write_text(json.dumps(meta), encoding="utf-8")


def test_every_pattern_runs_against_the_sandbox(live: int, tmp_path: Path) -> None:  # noqa: F811
    port = live
    folder = tmp_path / "shop"
    _ask(port, "POST", "/project/new", {"path": str(folder)})
    for name, text in (("orders", ORDERS_CSV), ("ledger", LEDGER_CSV), ("forms", FORMS_CSV)):
        csv = tmp_path / f"{name}.csv"
        csv.write_text(text, encoding="utf-8")
        _ask(port, "POST", "/sandbox/tables", {"from": "file", "path": str(csv)})
    for name, text in (("invoices", ORDERS_CSV), ("postings", LEDGER_CSV), ("visits", ORDERS_CSV)):
        csv = tmp_path / f"{name}.csv"
        csv.write_text(text, encoding="utf-8")
        _ask(port, "POST", "/sandbox/tables", {"from": "file", "path": str(csv), "name": name})
    warehouse = {"kind": "database", "connection": "Warehouse", "dialect": "sqlserver"}
    _mock_as(folder, "invoices", warehouse, "dbo")
    _mock_as(folder, "postings", warehouse, "dbo")
    _mock_as(folder, "visits", {"kind": "dataverse", "connection": "Sales CRM", "dialect": "dataverse"})

    # ----- the wizard's one read: the tables, then the patterns ranked, then a pattern's steps and code -----
    first = _ask(port, "POST", "/local-api/plan", {})
    assert [t["name"] for t in first["tables"]] == [
        "forms",
        "invoices",
        "ledger",
        "orders",
        "postings",
        "visits",
    ]
    assert len(first["patterns"]) == 9 and "ranked" not in first
    ranked = _ask(port, "POST", "/local-api/plan", {"table": "forms"})["ranked"]
    assert ranked[0]["pattern"] == "versions" and ranked[0]["why"].startswith("forms has version:")
    planned = _ask(port, "POST", "/local-api/plan", {"table": "orders", "pattern": "summary"})
    assert [s["id"] for s in planned["plan"]["steps"]] == ["group", "totals", "date", "period"]
    assert planned["problem"] is None and planned["added"] == ["summary_orders_by_region"]
    assert (
        planned["code"].startswith("# ===== orders: Summary")
        and "# pattern: summary of orders" in planned["code"]
    )
    assert [w["widget"] for w in planned["paired"]] == ["bar_chart", "data_table"]
    missing = _ask(
        port, "POST", "/local-api/plan", {"table": "orders", "pattern": "summary", "fields": {"totals": []}}
    )
    assert missing["problem"] == "Pick at least one total (count is one)." and missing["code"] == ""
    two = _ask(port, "POST", "/local-api/plan", {"table": "orders", "pattern": "reconcile"})
    assert {s["id"]: s["value"] for s in two["plan"]["steps"]}[
        "other"
    ] == "invoices"  # shares the most columns

    # ----- the agent's dry run: the code, nothing written -----
    before = (folder / "API.py").read_text(encoding="utf-8")
    dry = _ask(
        port,
        "POST",
        "/local-api/scaffold",
        {"table": "orders", "pattern": "search", "dry_run": True},
        agent=True,
    )
    assert dry["dry_run"] and dry["added"] == ["search_orders"] and "def search_orders(" in dry["code"]
    assert "from datetime import date" in dry["imports"]
    assert (folder / "API.py").read_text(encoding="utf-8") == before

    # ----- Add to API.py: every pattern -----
    for wanted, table, fields, other in CASES:
        body: dict[str, Any] = {"table": table, "pattern": wanted, "fields": fields}
        done = _ask(port, "POST", "/local-api/scaffold", body | ({"other": other} if other else {}))
        assert done["added"] and done["pattern"] == wanted, done
    month: dict[str, Any] = {"group": [], "date": "order_date", "period": "month"}
    extra: tuple[tuple[str, str, dict[str, Any], str | None], ...] = (
        ("summary", "invoices", month, None),  # one statement of T-SQL, through the mock
        ("reconcile", "invoices", {}, "postings"),  # the two joined by the source, in T-SQL
        ("summary", "visits", month, None),  # Dataverse has no SQL: DuckDB over the stream
        ("reconcile", "orders", {"key": ["order_id"], "compare": ["amount"]}, "postings"),  # two connections
    )
    for wanted, table, fields, other in extra:
        body = {"table": table, "pattern": wanted, "fields": fields} | ({"other": other} if other else {})
        assert _ask(port, "POST", "/local-api/scaffold", body)["added"], body
    text = (folder / "API.py").read_text(encoding="utf-8")
    compile(text, "API.py", "exec")
    assert text.count("from sab_api import") == 1  # the imports are written among its own, once
    state = _ask(port, "GET", "/local-api")
    assert state["problems"] == []
    by = {e["name"]: e for e in state["endpoints"]}
    # The APIs page labels an endpoint by its pattern; the data words say where DuckDB does the work.
    assert by["search_orders"]["pattern"] == {
        "id": "search",
        "label": "Search",
        "of": "orders",
        "role": "search",
    }
    assert (
        by["list_orders"]["pattern"]["role"] == "list" and by["approve_orders"]["pattern"]["role"] == "action"
    )
    assert by["summary_orders_by_month"]["data"] == ["The sandbox (plain DuckDB)"]
    assert by["summary_invoices_by_month"]["data"] == ["Mock of Warehouse (sqlserver)"]
    stream = "DuckDB does part of it over the stream (its source cannot)"
    assert by["summary_visits_by_month"]["data"] == ["Mock of Sales CRM (dataverse)", stream]
    assert by["reconcile_orders_postings"]["data"] == [
        "The sandbox (plain DuckDB)",
        "Mock of Warehouse (sqlserver)",
        stream,
    ]
    # The key the endpoints write by is the sandbox's too (versions: the thing and its version number).
    tables = {t["name"]: t for t in _ask(port, "GET", "/sandbox")["tables"]}
    assert [c["name"] for c in tables["forms"]["columns"] if c["key"]] == ["form_id", "version"]
    assert [c["name"] for c in tables["orders"]["columns"] if c["key"]] == ["order_id"]

    assert _ask(port, "POST", "/local-api/run", {})["running"]

    def call(method: str, path: str, body: Any = None, **query: Any) -> Any:
        return _ask(
            port, "POST", "/local-api/call", {"method": method, "path": path, "body": body, "query": query}
        )

    try:
        # ----- reconcile (before anything is written) -----
        counts = {"matched": 3, "differing": 1, "missing_in_orders": 1, "missing_in_ledger": 1}
        assert call("GET", "/reconcile/orders-ledger")["body"] == counts
        rows = call("GET", "/reconcile/orders-ledger/rows")["body"]
        assert [(r["order_id"], r["result"]) for r in rows] == [
            (2, "differing"),
            (5, "missing in ledger"),
            (9, "missing in orders"),
        ]
        assert rows[0]["amount_orders"] == 80.0 and rows[0]["amount_ledger"] == 85.0
        matched = call("GET", "/reconcile/orders-ledger/rows", show="matched", limit=2, offset=1)["body"]
        assert [r["order_id"] for r in matched] == [3, 4]
        assert call("GET", "/reconcile/orders-ledger/rows", show="nope")["status"] == 422
        # The same through T-SQL the mock runs, and through DuckDB over two connections' streams.
        assert call("GET", "/reconcile/invoices-postings")["body"] == {
            "matched": 3, "differing": 1, "missing_in_invoices": 1, "missing_in_postings": 1,
        }  # fmt: skip
        paged = call("GET", "/reconcile/invoices-postings/rows", limit=2, offset=1)["body"]
        assert [(r["order_id"], r["result"]) for r in paged] == [
            (5, "missing in postings"),
            (9, "missing in invoices"),
        ]
        assert call("GET", "/reconcile/orders-postings")["body"] == {
            "matched": 3, "differing": 1, "missing_in_orders": 1, "missing_in_postings": 1,
        }  # fmt: skip
        across = call("GET", "/reconcile/orders-postings/rows", show="differing")["body"]
        assert [(r["order_id"], r["amount_orders"], r["amount_postings"]) for r in across] == [
            (2, 80.0, 85.0)
        ]

        # ----- choices -----
        assert call("GET", "/orders/choices/region")["body"] == [
            {"region": "East", "rows": 2},
            {"region": "North", "rows": 2},
            {"region": "South", "rows": 1},
        ]
        assert call("GET", "/orders/choices/region", search="or")["body"] == [{"region": "North", "rows": 2}]

        # ----- search: the most literal path wins over /orders/{key} -----
        assert [r["order_id"] for r in call("GET", "/orders/search", q="Lar")["body"]] == [2]
        north = call("GET", "/orders/search", region="North", from_order_date="2026-02-01")["body"]
        assert [r["order_id"] for r in north] == [3] and north[0]["order_date"] == "2026-02-03"
        last = call("GET", "/orders/search", status="open", sort="amount", descending="true", limit=2)["body"]
        assert [r["order_id"] for r in last] == [4, 1]
        assert call("GET", "/orders/search", sort="nope")["status"] == 422
        assert call("GET", "/orders/3")["body"]["customer"] == "Cy Moss"

        # ----- summary: a plan the source folds; by month in its own SQL; by month over the stream -----
        assert call("GET", "/orders/summary/region")["body"] == [
            {"region": "East", "sum_amount": 140.0, "rows": 2},
            {"region": "North", "sum_amount": 160.5, "rows": 2},
            {"region": "South", "sum_amount": 200.0, "rows": 1},
        ]
        assert call("GET", "/orders/summary/region", region="South")["body"] == [
            {"region": "South", "sum_amount": 200.0, "rows": 1}
        ]
        months = [
            {"period": "2026-01-01", "sum_amount": 200.5, "rows": 2},
            {"period": "2026-02-01", "sum_amount": 240.0, "rows": 2},
            {"period": "2026-03-01", "sum_amount": 60.0, "rows": 1},
        ]
        for name in ("orders", "invoices", "visits"):
            assert call("GET", f"/{name}/summary/month")["body"] == months, name
            assert call("GET", f"/{name}/summary/month", since="2026-02-01")["body"] == months[1:], name

        # ----- export -----
        saved = call("GET", "/orders/export.csv")["body"]
        assert saved["download"] == "orders.csv" and saved["type"].startswith("text/csv")
        assert saved["text"].split("\r\n")[:2] == [
            "order_id,customer,region,status,order_date,amount",
            "1,Ada Fenn,North,open,2026-01-05,120.5",
        ]
        assert call("GET", "/orders/export.csv", limit=2)["body"]["text"].count("\r\n") == 3
        book = call("GET", "/orders/export.xlsx")["body"]
        assert book["download"] == "orders.xlsx" and book["bytes"] > 500 and "text" not in book

        # ----- bulk upload: a dry run with the problems, then all or none -----
        new = {"order_id": 6, "customer": "Flo Wren", "region": "West", "status": "open",
               "order_date": "2026-03-05", "amount": 10.0}  # fmt: skip
        bad = [new, {"order_id": 1, "amount": "lots"}, {"order_id": 6, "colour": "red"}]
        dry_run = call("POST", "/orders/bulk", bad, dry_run="true")
        assert dry_run["status"] == 200 and not dry_run["body"]["written"]
        assert dry_run["body"]["problems"] == [
            {"row": 2, "column": "amount", "problem": "is not a number"},
            {"row": 3, "column": "colour", "problem": "is not a column of orders"},
            {"row": 3, "column": "order_id", "problem": "repeats row 1's"},
        ]
        assert (dry_run["body"]["rows"], dry_run["body"]["inserted"], dry_run["body"]["updated"]) == (3, 1, 1)
        refused = call("POST", "/orders/bulk", bad)
        assert refused["status"] == 422 and refused["error"].startswith(
            "Nothing was written: 3 problems, the first: row 2 amount is not a number."
        )
        assert call("GET", "/orders/6")["status"] == 404  # none of it
        changed = {"order_id": 1, "customer": "Ada Fenn", "region": "North", "status": "open",
                   "order_date": "2026-01-05", "amount": 121.0}  # fmt: skip
        done = call("POST", "/orders/bulk", [new, changed])["body"]
        assert (done["written"], done["inserted"], done["updated"], done["problems"]) == (True, 1, 1, [])
        assert call("GET", "/orders/1")["body"]["amount"] == 121.0
        assert call("GET", "/orders/6")["body"]["order_date"] == "2026-03-05"

        # ----- action: every key checked, then one write -----
        assert call("POST", "/orders/approve", {"keys": [1, 2, 2]})["body"] == {"changed": 2, "keys": [1, 2]}
        assert call("GET", "/orders/2")["body"]["status"] == "approved"
        closed = call("POST", "/orders/approve", {"keys": [4, 3]})
        assert closed["status"] == 409 and closed["error"] == (
            "order_id 3 is not status open (1 of 2 are not): nothing changed."
        )
        assert call("GET", "/orders/4")["body"]["status"] == "open"  # all or none
        gone = call("POST", "/orders/approve", {"keys": [99]})
        assert (
            gone["status"] == 404 and gone["error"] == "No orders row has order_id 99 (1 of 1 are not there)."
        )
        assert call("POST", "/orders/approve", {"keys": []})["status"] == 422

        # ----- versions: earlier ones never change -----
        assert [r["version"] for r in call("GET", "/forms/1/versions")["body"]] == [2, 1]
        assert call("GET", "/forms/1/current")["body"]["title"] == "Intake two"
        made = call("POST", "/forms/1/versions", {"title": "Intake three", "version": 40})
        assert made["status"] == 201 and made["body"] == {"title": "Intake three", "form_id": 1, "version": 3}
        assert [r["title"] for r in call("GET", "/forms/1/versions")["body"]] == [
            "Intake three",
            "Intake two",
            "Intake",
        ]
        assert call("POST", "/forms/7/versions", {"title": "New"})["body"]["version"] == 1
        assert call("GET", "/forms/9/current")["status"] == 404
    finally:
        _ask(port, "POST", "/local-api/stop", {})
    log = _ask(port, "GET", "/sandbox")["log"]
    assert log["orders"] == {"inserted": 1, "updated": 3, "deleted": 0}
    assert log["forms"] == {"inserted": 2, "updated": 0, "deleted": 0}


# ===== exports: all nine for the three targets, run against the real connection =====


@pytest.fixture
def shop(tmp_path: Path) -> Iterator[tuple[TestClient, Path]]:
    """A project whose sandbox holds the made-up Shop connection's orders, ledger and forms (read once)."""
    database = tmp_path / "shop.sqlite"
    with sqlite3.connect(database) as made_up:
        made_up.execute(
            "CREATE TABLE orders (order_id INTEGER, customer TEXT, region TEXT, status TEXT, "
            "order_date TEXT, amount REAL)"
        )
        made_up.executemany(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)",
            [line.split(",") for line in ORDERS_CSV.strip().split("\n")[1:]],
        )
        made_up.execute("CREATE TABLE ledger (order_id INTEGER, amount REAL, posted TEXT)")
        made_up.executemany(
            "INSERT INTO ledger VALUES (?, ?, ?)",
            [line.split(",") for line in LEDGER_CSV.strip().split("\n")[1:]],
        )
        made_up.execute("CREATE TABLE forms (form_id INTEGER, version INTEGER, title TEXT)")
        made_up.executemany(
            "INSERT INTO forms VALUES (?, ?, ?)",
            [line.split(",") for line in FORMS_CSV.strip().split("\n")[1:]],
        )
    code = (
        "import sqlite3\nfrom pathlib import Path\n\n"
        'assert secret("password")\n'
        f'path = Path(r"{database}")\n'
        "conn = sqlite3.connect(path, check_same_thread=False)\n"
    )
    connection = {
        "name": "Shop", "kind": "sql", "template": "sqlite", "dialect": "sqlite", "code": code,
        "secrets": {"password": KEYRING_SECRET},
    }  # fmt: skip
    with memory_keyring(), make_client(tmp_path) as client:
        ok(client.post("/connections", json=connection, headers=AUTH))
        folder = tmp_path / "shop"
        ok(client.post("/project/new", json={"path": str(folder)}, headers=AUTH))
        for table in ("orders", "ledger", "forms"):
            body = {"from": "connection", "connection": "Shop", "table": table}
            ok(client.post("/sandbox/tables", json=body, headers=AUTH))
        yield client, folder


EXPORTED_CALLS = """
import base64, json
{setup}
def ask(method, path, query=None, body=None):
    status, kind, payload = send(method, path, query or {{}}, None if body is None else json.dumps(body))
    if kind.startswith("application/json"):
        return [status, json.loads(payload) if payload else None]
    return [status, kind, payload[:60] if isinstance(payload, str) else len(payload)]
out = {{
    "list": ask("GET", "/orders", {{"limit": "2"}}),
    "choices": ask("GET", "/orders/choices/region"),
    "search": ask("GET", "/orders/search", {{"q": "Lar"}}),
    "summary": ask("GET", "/orders/summary/region", {{"region": "East"}}),
    "reconcile": ask("GET", "/reconcile/orders-ledger"),
    "rows": ask("GET", "/reconcile/orders-ledger/rows", {{"limit": "2"}}),
    "csv": ask("GET", "/orders/export.csv", {{"limit": "1"}}),
    "xlsx": ask("GET", "/orders/export.xlsx"),
    "dry": ask("POST", "/orders/bulk", {{"dry_run": "true"}}, [{{"order_id": 1, "amount": "lots"}}]),
    "bulk": ask("POST", "/orders/bulk", None, [{{"order_id": 6, "customer": "Flo Wren", "region": "West",
                "status": "open", "order_date": "2026-03-05", "amount": 10.0}}]),
    "action": ask("POST", "/orders/approve", None, {{"keys": [1, 6]}}),
    "refused": ask("POST", "/orders/approve", None, {{"keys": [3]}}),
    "versions": ask("GET", "/forms/1/versions"),
    "new": ask("POST", "/forms/1/versions", None, {{"title": "Intake three"}}),
    "get": ask("GET", "/orders/6"),
}}
print(json.dumps(out))
"""
LAMBDA = """
import lambda_function
def send(method, path, query, body):
    event = {"httpMethod": method, "path": path, "queryStringParameters": query, "body": body}
    got = lambda_function.handler(event, None)
    payload = base64.b64decode(got["body"]) if got["isBase64Encoded"] else got["body"]
    return got["statusCode"], got["headers"].get("Content-Type", ""), payload
"""
AZURE = """
import function_app
import azure.functions as func
import sab_api
made = function_app.app.get_functions()
def send(method, path, query, body):
    found = sab_api.find(method, path)[0]
    fn = next(f.get_user_function() for f in made if f.get_function_name() == found.name)
    request = func.HttpRequest(method=method, url="https://x.azurewebsites.net" + path, params=query,
                               body=(body or "").encode())
    got = fn(request)
    payload = got.get_body()
    kind = got.mimetype or ""
    text = kind.startswith(("application/json", "text/"))
    return got.status_code, kind, payload.decode() if text else payload
"""
FASTAPI = """
from starlette.testclient import TestClient
import main
client = TestClient(main.app)
def send(method, path, query, body):
    got = client.request(method, path, params=query, content=body)
    kind = got.headers.get("content-type", "")
    return got.status_code, kind, got.text if kind.startswith(("application/json", "text/")) else got.content
"""


def test_every_pattern_exports_for_the_three_targets_and_runs_on_the_real_connection(
    shop: tuple[TestClient, Path], tmp_path: Path
) -> None:
    client, folder = shop
    cases = [c for c in CASES if c[2].get("period") is None]  # SQLite keeps its dates as text: no period
    for wanted, table, fields, other in cases:
        body = {"table": table, "pattern": wanted, "fields": fields} | ({"other": other} if other else {})
        done = ok(client.post("/local-api/scaffold", json=body, headers=AUTH))
        assert done["added"], done
    text = (folder / "API.py").read_text(encoding="utf-8")
    assert 'connection("Shop").read("orders"' in text
    assert 'FROM "orders" AS l' in text and 'FULL OUTER JOIN "ledger" AS r' in text  # Shop's own SQL
    stand = tmp_path / "standins"
    (stand / "azure" / "functions").mkdir(parents=True)
    (stand / "azure" / "__init__.py").write_text("", encoding="utf-8")
    (stand / "azure" / "functions" / "__init__.py").write_text(AZURE_STANDIN, encoding="utf-8")
    try:
        import fastapi  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        (stand / "fastapi").mkdir()
        (stand / "fastapi" / "__init__.py").write_text(
            FASTAPI_STANDIN + "\n__all__ = ['FastAPI', 'Request', 'Response']\n", encoding="utf-8"
        )
    answers = {}
    database = tmp_path / "shop.sqlite"
    untouched = database.read_bytes()
    for target, setup in (("aws_lambda", LAMBDA), ("azure_functions", AZURE), ("fastapi", FASTAPI)):
        done = ok(client.post("/local-api/export", json={"target": target}, headers=AUTH))
        place = Path(done["folder"])
        assert (place / "API.py").read_text(encoding="utf-8") == text  # the endpoints never change
        database.write_bytes(untouched)  # each target starts from the same made-up rows
        answers[target] = _run(place, EXPORTED_CALLS.format(setup=setup), stand)
    got = answers["aws_lambda"]
    assert got["list"] == [200, [
        {"order_id": 1, "customer": "Ada Fenn", "region": "North", "status": "open",
         "order_date": "2026-01-05", "amount": 120.5},
        {"order_id": 2, "customer": "Bo Larch", "region": "East", "status": "open",
         "order_date": "2026-01-20", "amount": 80.0},
    ]]  # fmt: skip
    assert got["choices"] == [200, [
        {"region": "East", "rows": 2}, {"region": "North", "rows": 2}, {"region": "South", "rows": 1},
    ]]  # fmt: skip
    assert [r["order_id"] for r in got["search"][1]] == [2]
    assert got["summary"] == [200, [{"region": "East", "sum_amount": 140.0, "rows": 2}]]
    assert got["reconcile"] == [
        200, {"matched": 3, "differing": 1, "missing_in_orders": 1, "missing_in_ledger": 1},
    ]  # fmt: skip
    assert [(r["order_id"], r["result"]) for r in got["rows"][1]] == [
        (2, "differing"),
        (5, "missing in ledger"),
    ]
    assert got["csv"][:2] == [200, "text/csv; charset=utf-8"]
    assert got["csv"][2].startswith("order_id,customer,region,status,order_date,amount\r\n1,Ada")
    assert got["xlsx"][:2] == [200, api_runtime.XLSX] and got["xlsx"][2] > 500
    assert got["dry"][1]["problems"] == [{"row": 1, "column": "amount", "problem": "is not a number"}]
    assert (got["bulk"][1]["written"], got["bulk"][1]["inserted"]) == (True, 1)
    assert got["action"] == [200, {"changed": 2, "keys": [1, 6]}]
    assert got["refused"][0] == 409
    assert [r["version"] for r in got["versions"][1]] == [2, 1]
    assert got["new"] == [201, {"title": "Intake three", "form_id": 1, "version": 3}]
    assert got["get"][1]["status"] == "approved" and got["get"][1]["customer"] == "Flo Wren"
    # The three targets answer alike.
    assert answers["azure_functions"] == got and answers["fastapi"] == got
