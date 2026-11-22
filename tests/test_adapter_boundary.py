"""The adapter's one rule, read like the layers test (Plans/adapter.plan.md: "every single data call and every
api payload in and out should travel through the adapter"): every place outside adapter.py that opens a
database driver or turns JSON into rows, found with ast.

Enforced for what moved: a local sandbox API's own process (api_host.py, sab_api) opens no driver and reaches
the sandbox only through the adapter (phase 3: the mock clients and the JSON op door went; connection(name) is
the adapter's Connection), and the endpoints the app writes and its example call only the adapter. The rest is
listed (run with -s to print it) for the later steps to move; docs/ideas.md has it."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "swissarmybench"
ROOTS = [PACKAGE, *sorted((PACKAGE.parents[1] / "extensions").glob("*/src/*"))]
ADAPTER = PACKAGE / "adapters" / "adapter.py"

DRIVERS = {
    "duckdb", "sqlite3", "psycopg", "psycopg2", "pymysql", "mysql", "pyodbc", "mssql_python", "pytds",
    "oracledb", "snowflake", "trino", "sqlalchemy", "deltalake", "databricks", "google", "pbixray",
}  # fmt: skip
# Calls that make rows of JSON-shaped values (records, pages), outside the adapter's from_json.
TO_ROWS = {"from_pylist", "from_records", "json_normalize", "read_json", "read_json_auto"}
IN_SQL = ("read_json", "read_json_auto", "json_transform", "from_json")  # SQL text that makes JSON rows


def _relative(path: Path) -> str:
    for root in ROOTS:
        if path.is_relative_to(root):
            return f"{root.name}/{path.relative_to(root).as_posix()}"
    return path.as_posix()


def _found(path: Path) -> dict[str, set[str]]:
    """What one file does: the drivers it imports, the JSON-to-rows calls it makes (real code, never the
    code it writes out as text)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    drivers: set[str] = set()
    rows: set[str] = set()
    sql: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            sql.update(word for word in IN_SQL if word + "(" in node.value)
        if isinstance(node, ast.Import):
            drivers.update(a.name.split(".")[0] for a in node.names if a.name.split(".")[0] in DRIVERS)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if node.module.split(".")[0] in DRIVERS:
                drivers.add(node.module.split(".")[0])
        elif (
            isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in TO_ROWS
        ):
            rows.add(
                node.func.attr
            )  # an attribute call: con.read_json, pa.Table.from_pylist (not read_json(request))
    return {"drivers": drivers, "rows": rows, "sql": sql}


def places() -> dict[str, dict[str, set[str]]]:
    """Every file outside the adapter that opens a driver or turns JSON into rows."""
    out: dict[str, dict[str, set[str]]] = {}
    for root in ROOTS:
        for path in sorted(root.rglob("*.py")):
            if path == ADAPTER:
                continue
            found = _found(path)
            if found["drivers"] or found["rows"] or found["sql"]:
                out[_relative(path)] = found
    return out


def test_the_places_outside_the_adapter_are_listed() -> None:
    listed = places()
    for name, found in listed.items():
        said = ", ".join(sorted(found["drivers"])) or "-"
        rows = ", ".join(sorted(found["rows"])) or "-"
        print(f"{name}: drivers {said}; JSON to rows {rows}; in SQL {', '.join(sorted(found['sql'])) or '-'}")
    assert "swissarmybench/adapters/adapter.py" not in listed
    assert listed, "the scan finds the places the later steps move"


def test_a_local_sandbox_apis_process_opens_no_driver() -> None:
    listed = places()
    for name in ("server/api_host.py", "server/api_runtime.py"):
        assert not listed.get(f"swissarmybench/{name}", {}).get("drivers"), name
    assert not (PACKAGE / "server" / "sandbox_clients.py").exists()  # the mock clients went (phase 3)


OLD_CLIENT = {"cursor", "execute", "executemany", "fetchone", "fetchall", "read_arrow", "rows", "fetch"}


def _client_calls(text: str) -> set[str]:
    return {
        n.func.attr
        for n in ast.walk(ast.parse(text))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in OLD_CLIENT
    }


def test_a_sandbox_api_reaches_its_data_only_through_the_adapter() -> None:
    """Phase 3: the sandbox's data door is the adapter's four calls (tables, read, query, write as Arrow), and
    the endpoints the app writes (New endpoint from a table) and its example app call only the adapter."""
    from swissarmybench.domain import api_scaffold as scaffold
    from swissarmybench.domain import local_api as rules

    routes = (PACKAGE / "server" / "routes_sandbox.py").read_text(encoding="utf-8")
    assert 'Route("/sandbox/data"' not in routes and 'DATA_PREFIX + "{key}",' not in routes
    columns: list[dict[str, Any]] = [
        {"name": "order_id", "type": "BIGINT", "key": True},
        {"name": "region", "type": "VARCHAR"},
    ]
    for source in (
        scaffold.Source("duckdb", "Sandbox"),
        scaffold.Source("database", "Warehouse", "sqlserver", "dbo"),
        scaffold.Source("dataverse", "Sales CRM", "dataverse"),
        scaffold.Source("sharepoint", "Team site"),
    ):
        block = scaffold.crud("orders", columns, source)
        assert not _client_calls(rules.scaffold("x") + block), source
    example = PACKAGE.parents[1] / "examples" / "forms_recon" / "API.py"
    assert not _client_calls(example.read_text(encoding="utf-8"))


ENGINE_MOVED = {
    "adapters/export.py": ("batches",),  # every export's rows (CSV, Excel, Parquet, Markdown)
    "adapters/datasets.py": ("query_table", "query_to_arrow_stream"),  # "+" tab, SQL box, a kernel's view
    # Phase 4: the engine's cursor (Adapted): a grid's windows, its steps' counts and the view cache, the SQL
    # box, the analyses and profiles all execute through it.
    "adapters/views.py": ("execute",),
}
DIRECT_ROWS = {"to_arrow_reader", "to_arrow_table", "fetch_arrow_table", "fetchall", "fetchmany", "fetchone"}


def test_the_engine_paths_that_moved_read_rows_only_through_the_adapter() -> None:
    """Phase 3, step 5 (the rule covers the engine too): an export's rows, a query made a table (the "+" tab,
    the SQL box) and a kernel's DuckDB SQL naming an open table are the adapter's query over the app's own
    DuckDB session, never a cursor's rows read directly."""
    for name, functions in ENGINE_MOVED.items():
        tree = ast.parse((PACKAGE / name).read_text(encoding="utf-8"))
        bodies = {f.name: f for f in ast.walk(tree) if isinstance(f, ast.FunctionDef)}
        for function in functions:
            called = {
                n.func.attr for n in ast.walk(bodies[function])
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            }  # fmt: skip
            assert "query" in called, f"{name} {function} reads through adapter.query"
            assert not called & DIRECT_ROWS, (
                f"{name} {function} reads rows itself: {sorted(called & DIRECT_ROWS)}"
            )


def _calls(path: str, function: str) -> set[str]:
    tree = ast.parse((PACKAGE / path).read_text(encoding="utf-8"))
    body = next(
        f
        for f in ast.walk(tree)
        if isinstance(f, ast.FunctionDef | ast.AsyncFunctionDef) and f.name == function
    )
    return {
        n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
        for n in ast.walk(body)
        if isinstance(n, ast.Call)
    }


def test_every_grid_query_and_engine_cursor_reaches_rows_through_the_adapter() -> None:
    """Phase 4, step 4 (the owner: "everything, the engine too"): every grid query (windows, counts, the
    view cache, the SQL box, profiles, analyses, regression, time series) is handed the adapted cursor, and
    the two engine paths that take a cursor themselves (an Analyze run, a highlight's check) adapt theirs."""
    assert "adapted" in _calls("services/workspace.py", "grid_query")
    assert "adapted" in _calls("services/analyze.py", "_on_view")
    assert "adapted" in _calls("services/grids.py", "set_highlights")
    assert "query" in _calls("adapters/views.py", "execute")


def test_a_file_connections_open_as_grid_reads_through_the_adapter() -> None:
    """Phase 4, step 3: a file connection's file is the adapter's Files read (DuckDB's types)."""
    assert {"read", "Files"} <= _calls("adapters/datasets.py", "load_adapted")
    text = (PACKAGE / "services" / "datasets.py").read_text(encoding="utf-8")
    found = text[text.index("class ConnectionTables") :]
    assert "adapted=True" in found[: found.index("def opened_from")]  # ConnectionTables.load_file


def test_open_as_grid_reads_every_dialect_the_adapter_knows_through_it() -> None:
    """Phase 2: a database connection's Open as grid is the adapter's read for DuckDB and each SQL dialect it
    folds a plan into (the old SELECT and COUNT text stays only for the dialects it does not know)."""
    from swissarmybench.adapters import adapter
    from swissarmybench.services import connections

    known = set(adapter.DIALECTS) - {"databricks"}  # Databricks' starter says dialect "other"
    assert known | {"duckdb"} == set(connections.ADAPTER_DIALECTS)


WRITES_OWN = {  # the Write starters that still write themselves, and why (docs/ideas.md "One adapter")
    "write_to_excel_sheet": "moves with the Excel module (Plans/excel.plan.md)",
}
STATEMENTS = {"execute", "executemany", "copy", "each_batch", "each_values", "each_where", "transaction"}


def test_the_write_starters_write_only_through_the_adapter() -> None:
    """Phase 4, step 1, and phase 5 (SQL Server and Trino): every Write function but the Excel sheet is a
    thin caller of the adapter's write (by_adapter: its planned() for the dry run, then adapter.write); none
    runs a statement itself: 15 of the 16."""
    functions = sorted((PACKAGE / "starters").glob("write_to_*.blade.py"))
    assert len(functions) == 16 and len(WRITES_OWN) == 1
    for path in functions:
        stem = path.name.removesuffix(".blade.py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = [n.func for n in ast.walk(tree) if isinstance(n, ast.Call)]
        called = {f.attr for f in calls if isinstance(f, ast.Attribute)} | {
            f.id for f in calls if isinstance(f, ast.Name)
        }
        if stem in WRITES_OWN:
            continue
        assert "by_adapter" in called or {"write", "planned"} <= called, f"{stem} writes through the adapter"
        assert stem in ("write_to_delta",) or not called & STATEMENTS, (
            f"{stem} runs statements itself: {sorted(called & STATEMENTS)}"
        )


def test_a_kernel_reaches_an_open_table_only_through_the_adapter() -> None:
    """Phase 2, Order 3: a kernel's DuckDB SQL naming an open table, and sab.table, read it as the adapter's
    source (the open tables' door); only sab.table's plain-client fallback names the view's address."""
    for name, allowed in (("client/sql_cell.py", 0), ("client/blades_client.py", 1)):
        text = (PACKAGE / name).read_text(encoding="utf-8")
        assert text.count("/workbench/tables/{") <= allowed, name  # the view's address, by name
