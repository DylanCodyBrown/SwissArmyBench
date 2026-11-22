"""The adapter's one rule, read like the layers test (Plans/adapter.plan.md: "every single data call and every
api payload in and out should travel through the adapter"): every place outside sab_adapter.py that opens a
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
ADAPTER = PACKAGE / "adapters" / "sab_adapter.py"

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
    assert "swissarmybench/adapters/sab_adapter.py" not in listed
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


def test_open_as_grid_reads_every_dialect_the_adapter_knows_through_it() -> None:
    """Phase 2: a database connection's Open as grid is the adapter's read for DuckDB and each SQL dialect it
    folds a plan into (the old SELECT and COUNT text stays only for the dialects it does not know)."""
    from swissarmybench.adapters import sab_adapter
    from swissarmybench.services import connections

    known = set(sab_adapter.DIALECTS) - {"databricks"}  # Databricks' starter says dialect "other"
    assert known | {"duckdb"} == set(connections.ADAPTER_DIALECTS)


def test_a_kernel_reaches_an_open_table_only_through_the_adapter() -> None:
    """Phase 2, Order 3: a kernel's DuckDB SQL naming an open table, and sab.table, read it as the adapter's
    source (the open tables' door); only sab.table's plain-client fallback names the view's address."""
    for name, allowed in (("client/sql_cell.py", 0), ("client/blades_client.py", 1)):
        text = (PACKAGE / name).read_text(encoding="utf-8")
        assert text.count("/workbench/tables/{") <= allowed, name  # the view's address, by name
