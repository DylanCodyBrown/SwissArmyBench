"""SQL cells on a connection, and DAX cells on a Power BI workspace's dataset, in Jupyter and
IPython: pick the connection once, write only SQL (or DAX).

    %%sql Warehouse                    # the whole cell runs on the Warehouse connection
    SELECT TOP 10 * FROM sales.orders

    %sql_connect Warehouse             # the default: later cells need no name
    %%sql -> late                      # the result is also kept as `late`
    SELECT * FROM sales.orders WHERE shipped > due

    %%sql "Budget workbook" --grid     # a workbook: each sheet is a table; --grid opens the result
    SELECT region, sum(amount) FROM "Forecast" GROUP BY region

    %sql_connections                   # the connections a cell can use, and what each one is

    %%dax Finance/Sales model          # DAX on one dataset of the Power BI workspace "Finance"
    EVALUATE TOPN(10, 'Sales')

    %%dax "Finance/Sales model" -> by_region --grid      # the same options as a SQL cell

Connections are added in the app (the Application row's Connections). What runs the SQL depends on
what the connection's code makes:

    a database connection   the database itself, in its own SQL: any DB-API connection (SQL Server,
                            PostgreSQL, MySQL, Oracle, SQLite, Snowflake, Redshift, Databricks, Trino,
                            Teradata, Db2, HANA, Vertica, ODBC...), DuckDB, BigQuery, ClickHouse, Spark,
                            and SQLAlchemy engines
    a file (a path)         DuckDB, in this Python: a CSV, text, Parquet or JSON file is a table named
                            after the file; a workbook's sheets are tables named after the sheets; a
                            folder's files are tables named after the files (also `"folder"."file.csv"`,
                            as the connection's catalog names them)
    a table (DataFrame)     a blade that makes one: DuckDB, in this Python, the table under its
                            variable's name
    a Power BI workspace    one of its datasets, named after the connection and a slash
                            (`Finance/Sales model`; a workspace with one dataset needs no name), in a
                            `%%dax` cell, which holds DAX, not SQL: `EVALUATE TOPN(10, 'Sales')`

A database statement that returns no rows (an UPDATE, an INSERT) is committed and says how many rows it
changed. `%%sql` is taken only when no other extension has it (JupySQL keeps its own); `%%sag` always
works. The same, outside a notebook: `sag.sql("Warehouse", "SELECT ...")`, and
`sag.dax("Finance/Sales model", "EVALUATE ...")`. Each connection is opened
once per Python session (`%sql_connect Warehouse` opens it again). Standard library only: DuckDB and
pandas are imported when a cell needs them, from this Python.
"""

from __future__ import annotations

import os
import re
import shlex
import sys
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

from swissarmygrid.client import blades_client

# The file kinds a cell reads, by suffix (DuckDB's readers; a workbook through pandas).
FILE_READERS: dict[str, str] = {
    ".csv": "read_csv_auto",
    ".tsv": "read_csv_auto",
    ".txt": "read_csv_auto",
    ".parquet": "read_parquet",
    ".json": "read_json_auto",
    ".jsonl": "read_json_auto",
    ".ndjson": "read_json_auto",
}
WORKBOOKS: frozenset[str] = frozenset({".xlsx", ".xlsm", ".xls"})
FILE_TEMPLATES: dict[str, str] = {
    "csv": "a CSV file",
    "excel": "a workbook",
    "parquet": "a Parquet file",
    "json": "a JSON file",
    "folder": "a folder of files",
}
_RESERVED_SCHEMAS = frozenset({"main", "temp", "system", "information_schema", "pg_catalog"})
_TARGET = re.compile(r"^[A-Za-z_]\w*$")


class SqlCellError(Exception):
    """A cell that can't run as written (the message says why and what to do)."""


@dataclass
class Connection:
    """A connection, opened in this Python: what runs the SQL and the tables it names."""

    name: str
    kind: str  # "database", "files" or "tables"
    target: Any  # what its code made (a database), or the DuckDB connection over its files or tables
    describe: str
    workbooks: dict[str, float] = field(default_factory=dict)  # a workbook's path -> when it was read
    sources: list[Path] = field(default_factory=list)
    language: str = "sql"  # "dax": a Power BI workspace's dataset


_connections: dict[str, Connection] = {}
_workspaces: dict[str, Any] = {}  # a Power BI workspace, signed in once for all its datasets
_default: list[str] = []  # the %sql_connect choice (one name, or none)


# ===== the cell's first line =====


@dataclass(frozen=True)
class CellLine:
    name: str | None  # None: the default connection
    target: str | None  # `-> name`: keep the result as this variable
    grid: bool  # --grid: open the result as a grid


def parse_line(line: str) -> CellLine:
    """`Warehouse`, `"My warehouse" -> late --grid`, `-> late`, `` (the default)."""
    try:
        words = shlex.split(line, posix=True)
    except ValueError as error:
        raise SqlCellError(f"Read the line as: %%sql <connection> [-> name] [--grid] ({error}).") from None
    grid = "--grid" in words
    words = [w for w in words if w != "--grid"]
    target: str | None = None
    if "->" in words:
        at = words.index("->")
        after = words[at + 1 :]
        if len(after) != 1 or not _TARGET.match(after[0]):
            raise SqlCellError("After -> put one Python name for the result: %%sql Warehouse -> orders.")
        target, words = after[0], words[:at]
    unknown = [w for w in words if w.startswith("--")]
    if unknown:
        raise SqlCellError(f"{unknown[0]} is not an option here; the one option is --grid.")
    return CellLine(" ".join(words) or None, target, grid)


# ===== opening a connection =====


def _record(name: str) -> dict[str, Any]:
    """The connection as the connections list describes it (kind, template, variable, dialect): no code
    and no secrets. A blade that is not a connection may still make a table (it is tried when used)."""
    for b in blades_client._call("GET", "/connections")["connections"]:
        if str(b["name"]).casefold() == name.casefold():
            return dict(b)
    for b in blades_client._call("GET", "/blades")["blades"]:
        if str(b["name"]).casefold() == name.casefold():
            return dict(b)
    raise SqlCellError(f"No connection is named {name!r}. %sql_connections lists the ones a cell can use.")


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _duckdb() -> Any:
    try:
        import duckdb
    except ImportError:
        raise SqlCellError(
            f"A file or table's SQL runs in DuckDB in this Python: {sys.executable} -m pip install duckdb"
        ) from None
    return duckdb


def _is_table(value: Any) -> bool:
    """A DataFrame-like table (pandas, polars, Arrow): something DuckDB reads by its variable name."""
    module = type(value).__module__.split(".")[0]
    return module in ("pandas", "polars", "pyarrow") and hasattr(value, "columns")


def _files_in(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(
            p for p in path.iterdir() if p.is_file() and p.suffix.lower() in {*FILE_READERS, *WORKBOOKS}
        )
    return [path]


def _view(con: Any, schema: str | None, table: str, select: str) -> None:
    """The table by its bare name (the first one to claim it) and as the connection's catalog names it."""
    names = [_quote(table)]
    if schema and schema.lower() not in _RESERVED_SCHEMAS:
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {_quote(schema)}")
        names.append(f"{_quote(schema)}.{_quote(table)}")
    taken = {
        r[0].lower()
        for r in con.execute("SELECT view_name FROM duckdb_views() WHERE schema_name = 'main'").fetchall()
    }
    for i, name in enumerate(names):
        if i == 0 and table.lower() in taken:
            continue
        con.execute(f"CREATE OR REPLACE VIEW {name} AS {select}")


def _read_workbook(con: Any, path: Path, in_folder: bool) -> None:
    """A workbook's sheets as tables (pandas reads them; reread when the file changes)."""
    try:
        import pandas as pd
    except ImportError:
        raise SqlCellError(
            f"A workbook is read with pandas: {sys.executable} -m pip install pandas openpyxl"
        ) from None
    try:
        sheets = pd.read_excel(path, sheet_name=None)
    except ImportError as error:
        raise SqlCellError(f"{error} ({sys.executable} -m pip install openpyxl)") from None
    for i, (sheet, frame) in enumerate(sheets.items()):
        hidden = f"__sag_sheet_{abs(hash((str(path), str(sheet))))}"
        con.register(hidden, frame)
        if in_folder:  # a folder's catalog reads a workbook's first sheet, by the file's name
            if i == 0:
                _view(con, path.parent.name, path.name, f"SELECT * FROM {hidden}")
                _view(con, None, path.stem, f"SELECT * FROM {hidden}")
            _view(con, path.stem, str(sheet), f"SELECT * FROM {hidden}")
        else:
            _view(con, path.stem, str(sheet), f"SELECT * FROM {hidden}")


def _open_files(name: str, value: Any) -> Connection:
    path = Path(value).expanduser()
    if not path.exists():
        raise SqlCellError(
            f"{name} points at {path}, which is not there. Change its path in the app's Connections."
        )
    if not path.is_dir() and path.suffix.lower() not in {*FILE_READERS, *WORKBOOKS}:
        raise SqlCellError(
            f"{name} points at {path.name}: a cell reads CSV, text, Parquet, JSON and Excel files, "
            "or a folder of them."
        )
    con = _duckdb().connect()
    found = Connection(name, "files", con, "", sources=_files_in(path))
    in_folder = path.is_dir()
    for file in found.sources:
        reader = FILE_READERS.get(file.suffix.lower())
        if reader:
            select = f"SELECT * FROM {reader}({_literal(str(file))})"
            if in_folder:
                _view(con, path.name, file.name, select)
            _view(con, None if in_folder else file.parent.name, file.stem, select)
        else:
            _read_workbook(con, file, in_folder)
            found.workbooks[str(file)] = file.stat().st_mtime
    what = "a folder" if in_folder else "a workbook" if path.suffix.lower() in WORKBOOKS else "a file"
    found.describe = f"{what} ({path}), read by DuckDB here: {', '.join(tables(found)) or 'no tables'}"
    return found


def _open_tables(name: str, value: Any, variable: str) -> Connection:
    con = _duckdb().connect()
    frames = value if isinstance(value, dict) else {variable or "result": value}
    for name, frame in frames.items():
        con.register(str(name), frame)
    return Connection(
        name,
        "tables",
        con,
        f"tables made in this Python ({', '.join(map(str, frames))}), read by DuckDB here",
    )


def _runs_sql(value: Any) -> bool:
    module = type(value).__module__
    return callable(getattr(value, "cursor", None)) or module.startswith(
        ("duckdb", "clickhouse_connect", "google.cloud.bigquery", "pyspark", "sqlalchemy")
    )


def _language(dialect: Any) -> str:
    """What a database connection's cells are written in: its SQL."""
    return "" if not dialect or dialect == "other" else f" ({dialect} SQL)"


def _open_dataset(label: str, value: Any, dataset: str) -> Connection:
    """One dataset of a Power BI workspace (the connection's own `dataset(name)`): what a DAX cell
    runs on. No dataset named: the workspace's one; with several, refused, naming them."""
    made = "a Power BI dataset (DAX)"
    lister = getattr(value, "datasets", None)
    if not callable(lister):  # a connection that is one dataset by itself (saved before workspaces)
        if dataset:
            raise SqlCellError(f"{label} is one dataset, not a workspace: name it alone, as {label}.")
        return Connection(label, "database", value, made, language="dax")
    listed = [str(d["name"]) for d in lister()]
    if not dataset:
        if len(listed) != 1:
            raise SqlCellError(
                f"{label} is a Power BI workspace with {len(listed)} datasets: name one, as "
                f"{label}/{listed[0] if listed else '<dataset>'}. It has: {', '.join(listed) or 'none'}."
            )
        dataset = listed[0]
    try:
        target = value.dataset(dataset)
    except Exception as error:  # its own words: the workspace has no such dataset, and what it has
        raise SqlCellError(f"{label}: {error}") from None
    return Connection(f"{label}/{target.name}", "database", target, made, language="dax")


def open_connection(name: str, fresh: bool = True) -> Connection:
    """Run the connection's code in this Python and keep what it makes for the cells to use. A Power
    BI workspace's dataset is named after the connection: `Finance/Sales model`; the workspace is
    signed in to once for all its datasets (`fresh`: again)."""
    base, _, dataset = name.partition("/")
    record = _record(base.strip())
    label, kind = str(record["name"]), str(record.get("kind", "other"))
    if kind in ("vault", "secret", "analysis"):
        raise SqlCellError(
            f"{label} is a {kind} blade, not a connection. %sql_connections lists the connections."
        )
    dax = record.get("dialect") == "dax"
    if dataset.strip() and not dax:
        raise SqlCellError(f"{label} is not a Power BI workspace: name it alone, as {label}.")
    value = None if fresh or not dax else _workspaces.get(label.casefold())
    if value is None:
        value = blades_client.blade(label)
    if dax:
        _workspaces[label.casefold()] = value
        found = _open_dataset(label, value, dataset.strip())
        _connections[" ".join(name.split()).casefold()] = found
    elif isinstance(value, (str, os.PathLike)):
        found = _open_files(label, value)
    elif _is_table(value) or (
        isinstance(value, dict) and value and all(_is_table(v) for v in value.values())
    ):
        found = _open_tables(label, value, str(record.get("variable") or ""))
    elif _runs_sql(value):
        made = f"{type(value).__module__.split('.')[0]} connection"
        found = Connection(label, "database", value, made + _language(record.get("dialect")))
    else:
        raise SqlCellError(
            f"{label} makes a {type(value).__name__}, which can't run SQL. A cell can use a database "
            "connection, a file or folder path, or a table (DataFrame)."
        )
    _connections[found.name.casefold()] = found
    return found


def connection(name: str | None) -> Connection:
    """The connection, opened on first use; no name: the %sql_connect one."""
    if name is None:
        if not _default:
            raise SqlCellError(
                "Name the connection (%%sql Warehouse) or choose one first: %sql_connect Warehouse."
            )
        name = _default[0]
    return _connections.get(" ".join(name.split()).casefold()) or open_connection(name, fresh=False)


def tables(found: Connection) -> list[str]:
    """The table names a files or tables connection offers (bare names first)."""
    if found.kind == "database":
        return []
    rows = found.target.execute(
        "SELECT schema_name, view_name FROM duckdb_views() WHERE NOT internal "
        "UNION ALL SELECT schema_name, table_name FROM duckdb_tables() WHERE NOT internal"
    ).fetchall()
    # A registered DataFrame is a view too (temporary, in main).
    names = [t if s == "main" else f"{s}.{t}" for s, t in rows if not t.startswith("__sag_")]
    return list(dict.fromkeys(sorted(names, key=lambda n: ("." in n, n.lower()))))


def columns(found: Connection) -> dict[str, list[str]]:
    """Each table's columns, for completion (files and tables connections only)."""
    out: dict[str, list[str]] = {}
    for name in tables(found):
        try:
            described = found.target.execute(
                f"DESCRIBE SELECT * FROM {'.'.join(_quote(p) for p in name.split('.', 1))}"
            ).fetchall()
        except Exception:  # noqa: S112 (a table that can't be described offers no columns)
            continue
        out[name] = [str(r[0]) for r in described]
    return out


# ===== running a cell =====


def _frame(names: list[str], rows: list[Any]) -> Any:
    """Rows as a pandas DataFrame when pandas is here, else a list of dicts."""
    try:
        import pandas as pd
    except ImportError:
        return [dict(zip(names, row, strict=False)) for row in rows]
    return pd.DataFrame.from_records([tuple(r) for r in rows], columns=names)


def _refresh(found: Connection) -> None:
    """A workbook saved since it was read: read it again (CSV, Parquet and JSON are read on every query)."""
    for path, when in list(found.workbooks.items()):
        file = Path(path)
        if file.exists() and file.stat().st_mtime != when:
            _read_workbook(
                found.target,
                file,
                file.parent in {p.parent for p in found.sources} and len(found.sources) > 1,
            )
            found.workbooks[path] = file.stat().st_mtime


def _duck_result(relation: Any) -> Any:
    if relation is None:  # a statement with no result
        return None
    try:
        return relation.df()
    except ImportError:
        return _frame(list(relation.columns), relation.fetchall())


def _run_database(target: Any, sql: str) -> Any:
    module = type(target).__module__
    if module.startswith("duckdb"):
        return _duck_result(target.sql(sql))
    if module.startswith("clickhouse_connect"):
        return target.query_df(sql)
    if module.startswith("google.cloud.bigquery"):
        return target.query(sql).to_dataframe()
    if module.startswith("pyspark"):
        return target.sql(sql).toPandas()
    if module.startswith("sqlalchemy"):
        text = import_module("sqlalchemy").text  # only an engine's own Python has it

        with target.begin() as live:
            result = live.execute(text(sql))
            if not result.returns_rows:
                return f"{result.rowcount} row(s) changed."
            return _frame(list(result.keys()), result.fetchall())
    cursor = target.cursor()
    try:
        cursor.execute(sql)
        if cursor.description is None:  # an UPDATE, INSERT, CREATE: no rows
            commit = getattr(target, "commit", None)
            if callable(commit):
                commit()
            count = getattr(cursor, "rowcount", -1)
            return f"{count} row(s) changed." if isinstance(count, int) and count >= 0 else "Done."
        return _frame([str(d[0]) for d in cursor.description], cursor.fetchall())
    finally:
        close = getattr(cursor, "close", None)
        if callable(close):
            close()


def run(found: Connection, sql: str) -> Any:
    """The SQL on the connection: a DataFrame (or rows), or a line saying what changed."""
    text = sql.strip()
    if not text:
        raise SqlCellError(f"The cell has no {'DAX' if found.language == 'dax' else 'SQL'} to run.")
    if found.kind == "database":
        return _run_database(found.target, text.rstrip(";") if text.count(";") == 1 else text)
    _refresh(found)
    return _duck_result(found.target.sql(text))


def sql(connection_name: str, query: str) -> Any:
    """Run `query` on a connection in this Python: `sag.sql("Warehouse", "SELECT ...")`. A DataFrame (or
    rows, without pandas), or a line saying what changed."""
    return run(connection(connection_name), query)


def _not_dax(found: Connection) -> SqlCellError:
    return SqlCellError(
        f"{found.name} is not a Power BI workspace's dataset, so it takes SQL, not DAX: use a SQL cell "
        "(%%sql) or sag.sql()."
    )


def dax(dataset_name: str, query: str) -> Any:
    """Run a DAX `query` on one dataset of a Power BI workspace connection, in this Python:
    `sag.dax("Finance/Sales model", "EVALUATE TOPN(10, 'Sales')")` (the connection's name, a slash,
    the dataset's name or id; a workspace with one dataset needs only the connection's name). A
    DataFrame (or rows, without pandas)."""
    found = connection(dataset_name)
    if found.language != "dax":
        raise _not_dax(found)
    return run(found, query)


# ===== the magics =====


def _stop(message: str) -> Exception:
    """IPython's short error (one line, no traceback; Run all stops there), or ours outside it."""
    try:
        usage: type[Exception] = import_module("IPython.core.error").UsageError
    except ImportError:
        usage = SqlCellError
    return usage(message)


def _cell(shell: Any, line: str, cell: str, dax: bool = False) -> Any:
    """A `%%sql` cell, or (`dax`) a `%%dax` cell: the same in every way but the language it holds."""
    what = "DAX cell" if dax else "SQL cell"
    try:
        parsed = parse_line(line)
        if dax and parsed.name is None and not _default:
            raise SqlCellError("Name the dataset: %%dax <connection>/<dataset>.")
        found = connection(parsed.name)
        if dax and found.language != "dax":
            raise _not_dax(found)
    except SqlCellError as error:
        raise _stop(f"{what}: {error}") from None
    try:
        result = run(found, cell)
    except SqlCellError as error:
        raise _stop(f"{what}: {error}") from None
    except Exception as error:  # the database's own refusal, in its words
        raise _stop(f"{found.name}: {type(error).__name__}: {error}") from None
    if isinstance(result, str):
        print(f"{found.name}: {result}")
        return None
    if parsed.target:
        shell.user_ns[parsed.target] = result
    if parsed.grid and result is not None:
        from swissarmygrid.client.push_client import push

        print(push(result, name=parsed.target or f"{found.name} result"))
    return result


def _connect(line: str) -> None:
    name = " ".join(shlex.split(line)) if line.strip() else ""
    if not name:
        print(
            f"The default connection: {_default[0] if _default else 'none'}. "
            "%sql_connect <connection> sets it."
        )
        return
    try:
        found = open_connection(name)  # opened again: a fresh connection, its latest code
    except SqlCellError as error:
        print(f"SQL cell: {error}", file=sys.stderr)
        return
    _default[:] = [found.name]
    print(f"%%sql cells now run on {found.name}: {found.describe}.")


def listing() -> list[tuple[str, str]]:
    """The connections a cell can use and what each is: databases, then files."""
    out = []
    for c in blades_client._call("GET", "/connections")["connections"]:
        if c.get("connection") == "database" and c.get("dialect") == "dax":
            what = f"a Power BI workspace: a DAX cell names a dataset, %%dax {c['name']}/<dataset>"
        elif c.get("connection") == "database":
            what = "database" + _language(c.get("dialect"))
        else:
            what = f"{FILE_TEMPLATES.get(str(c.get('template')), 'a file')}, read by DuckDB here"
        out.append((str(c["name"]), what))
    return out


def _connections_magic(_line: str) -> None:
    rows = listing()
    if not rows:
        print("No connections yet: add one in the app (the Application row's Connections).")
        return
    width = max(len(n) for n, _ in rows)
    for name, what in rows:
        mark = " *" if _default and _default[0].casefold() == name.casefold() else "  "
        print(f"{mark} {name.ljust(width)}  {what}")


_registered: list[Any] = []


def register(shell: Any) -> list[str]:
    """Add the magics to this IPython: %%sag always, %%sql and %%dax where no other extension has
    them."""
    if any(s is shell for s in _registered):
        return []
    names: list[str] = []

    def cell(line: str, cell_text: str) -> Any:
        return _cell(shell, line, cell_text)

    def dax_cell(line: str, cell_text: str) -> Any:
        return _cell(shell, line, cell_text, dax=True)

    for name in ("sag", "sql", "dax"):
        if name == "sag" or shell.find_cell_magic(name) is None:
            shell.register_magic_function(
                dax_cell if name == "dax" else cell, magic_kind="cell", magic_name=name
            )
            names.append(f"%%{name}")
    for prefix in ("sag", "sql"):
        for suffix, fn in (("connect", _connect), ("connections", _connections_magic)):
            name = f"{prefix}_{suffix}"
            if prefix == "sag" or shell.find_line_magic(name) is None:
                shell.register_magic_function(fn, magic_kind="line", magic_name=name)
                names.append(f"%{name}")
    _registered.append(shell)
    return names


def autostart() -> None:
    """On import in Jupyter or IPython, unless SWISSARMYGRID_SQL_CELL=0."""
    if os.environ.get("SWISSARMYGRID_SQL_CELL", "") == "0":
        return
    module = sys.modules.get("IPython")
    get = getattr(module, "get_ipython", None) if module is not None else None
    shell = get() if callable(get) else None
    if shell is not None and hasattr(shell, "register_magic_function"):
        register(shell)
