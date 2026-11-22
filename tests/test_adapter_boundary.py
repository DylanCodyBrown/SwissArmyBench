"""The adapter's one rule, read like the layers test (Plans/adapter.plan.md: "every single data call and every
api payload in and out should travel through the adapter"): every place outside sab_adapter.py that opens a
database driver or turns JSON into rows, found with ast.

Phase 1 enforces it only for what moved: a local sandbox API's own process (api_host.py, the mocks,
sab_api) opens no driver, and the mocks' calls that moved (every SQL mock's tables() and columns(), the
SharePoint mock's reads and writes) reach the sandbox only through the adapter. The rest is listed (run with
-s to print it) for the later steps to move; docs/ideas.md has it as of 2026-11-21."""

from __future__ import annotations

import ast
from pathlib import Path

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
    for name in ("server/api_host.py", "server/sandbox_clients.py", "server/api_runtime.py"):
        assert not listed.get(f"swissarmybench/{name}", {}).get("drivers"), name


MOVED = {
    "_Listing": ("_listed", "tables", "columns"),
    "MockSharePoint": ("tables", "rows", "read", "create", "update", "delete", "_write", "_typed"),
}
OLD_DOOR = {"ask", "_ask", "_rows", "_arrow", "_frame", *TO_ROWS}  # the JSON door and its row builders


def test_the_mocks_calls_that_moved_reach_the_sandbox_only_through_the_adapter() -> None:
    tree = ast.parse((PACKAGE / "server" / "sandbox_clients.py").read_text(encoding="utf-8"))
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    for class_name, methods in MOVED.items():
        bodies = {f.name: f for f in classes[class_name].body if isinstance(f, ast.FunctionDef)}
        for method in methods:
            called = {
                n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
                for n in ast.walk(bodies[method])
                if isinstance(n, ast.Call)
            }
            assert not called & OLD_DOOR, f"{class_name}.{method} calls {sorted(called & OLD_DOOR)}"


def test_open_as_grid_reads_every_dialect_the_adapter_knows_through_it() -> None:
    """Phase 2: a database connection's Open as grid is the adapter's read for DuckDB and each SQL dialect it
    folds a plan into (the old SELECT and COUNT text stays only for the dialects it does not know)."""
    from swissarmybench.adapters import sab_adapter
    from swissarmybench.services import connections

    known = set(sab_adapter.DIALECTS) - {"databricks"}  # Databricks' starter says dialect "other"
    assert known | {"duckdb"} == set(connections.ADAPTER_DIALECTS)
