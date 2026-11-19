"""`sab.load`, `sab.blade` and `sab.blades`: catalogs and blades from any Python (plan decisions 14-17).

    sab.load(columns_frame, name="Warehouse", dialect="sqlserver")   # a searchable catalog
    conn = sab.blade("Warehouse")                                     # a saved blade, run here
    sab.blade("Monthly sales")      # a table blade: its result is also the variable its table name says
    sab.blade("Azure vault")        # a vault blade: sets its environment variables, gives their names
    sab.blade("Warehouse login")    # a secret blade: asks for any value this Python does not have yet
    api = sab.connection("Orders API")                                # a connection (the same, by its name)
    orders = sab.read("Orders API", "orders")       # a table, by a connection's own Read a table

A blade's code runs in this Python, so its driver must be installed here; a missing one is named with
the command that installs it. Secret values never print: a vault or secret blade hands back the
names it set, not the values. Standard library only, like the rest of the client.
"""

from __future__ import annotations

import functools
import getpass
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from swissarmybench.adapters.blade_run import (
    BladeRunError,
    list_tables,
    read_table,
    run_code,
    run_vault,
    set_variables,
)
from swissarmybench.client import connection_use, standalone
from swissarmybench.client.kernel_values import is_table
from swissarmybench.client.push_client import (
    ServerNotRunningError,
    _arrow_bytes,
    _prepared_frame,
    _records_json,
    _source_kind,
    _to_arrow,
    ensure_server,
)
from swissarmybench.domain.blades import missing_module_hint
from swissarmybench.domain.python_connections import env_reads

_TIMEOUT_SECONDS: float = 300.0


def _call(method: str, path: str, body: bytes | None = None, content_type: str = "application/json") -> Any:
    info = ensure_server()
    request = urllib.request.Request(
        f"http://127.0.0.1:{info['port']}{path}",
        data=body,
        method=method,
        headers={"Authorization": f"Bearer {info['token']}", "Content-Type": content_type},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 (fixed http://127.0.0.1 URL)
            return json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        message = error.read().decode("utf-8", "replace")
        if error.code == 404:
            raise LookupError(message) from None
        raise RuntimeError(f"Swiss Army Bench refused ({error.code}): {message}") from None


def _call_bytes(path: str) -> bytes:
    """A GET whose answer is bytes (a connection's table as Arrow, for a kernel's DuckDB)."""
    info = ensure_server()
    request = urllib.request.Request(
        f"http://127.0.0.1:{info['port']}{path}", headers={"Authorization": f"Bearer {info['token']}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 (fixed http://127.0.0.1 URL)
            return bytes(response.read())
    except urllib.error.HTTPError as error:
        message = error.read().decode("utf-8", "replace")
        raise RuntimeError(f"Swiss Army Bench refused ({error.code}): {message}") from None


def _quote(name: str) -> str:
    return urllib.parse.quote(name, safe="")


def load(catalog: object, name: str, *, dialect: str | None = None) -> str:
    """Load a source database's names and types as a searchable catalog. Returns the explorer's address.

    `catalog` is any table with, per row, one column of the source: its table and column, and usually
    its schema and type. An INFORMATION_SCHEMA.COLUMNS result works as it is, as do Oracle's
    ALL_TAB_COLUMNS and plain schema/table/column/type frames. `dialect` (sqlserver, postgres, mysql,
    sqlite, duckdb, snowflake, oracle, trino) lets the agent quote SQL for the source.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Name the catalog: sab.load(frame, name='Warehouse').")
    try:
        table = _to_arrow(catalog)
    except ImportError:
        table = None
    if table is not None:
        body, content_type = _arrow_bytes(table), "application/vnd.apache.arrow.stream"
    elif _source_kind(catalog) == "records":
        body, content_type = _records_json(catalog), "application/json"  # type: ignore[arg-type]
    elif _source_kind(catalog) == "pandas":
        frame: Any = _prepared_frame(catalog)
        body, content_type = frame.to_json(orient="split", default_handler=str).encode(), "application/json"
    else:
        raise ImportError(
            "Install pyarrow to load anything other than a pandas DataFrame or a list of dicts."
        )
    query = f"?dialect={_quote(dialect)}" if dialect else ""
    answer = _call("PUT", f"/catalogs/{_quote(name)}{query}", body, content_type)
    return str(answer.get("url") or "")


def blades(tag: str | None = None, search: str | None = None) -> list[str]:
    """The names of the blades (saved ones and those in your blade folders), favourites first.

    `tag` keeps those with that tag (ignoring case); `search` keeps those whose name, description or a
    tag contains the text: `sab.blades(search="orders-function-app")`.
    """
    found = _call("GET", "/blades")["blades"]
    if tag:
        found = [b for b in found if tag.casefold() in (t.casefold() for t in b.get("tags", []))]
    if search:
        text = search.casefold()
        found = [
            b
            for b in found
            if text in str(b["name"]).casefold()
            or text in str(b.get("description", "")).casefold()
            or any(text in t.casefold() for t in b.get("tags", []))
        ]
    found.sort(key=lambda b: (not b.get("pinned"), str(b["name"]).casefold()))
    return [str(b["name"]) for b in found]


def _spec(name: str) -> dict[str, Any]:
    """Everything needed to run a blade here: from the app, or, when it is not running, from this
    computer's saved connections, the blade folders and the starter pack (client/standalone.py)."""
    try:
        spec: dict[str, Any] = _call("GET", f"/blades/{_quote(name)}/python")
    except ServerNotRunningError:
        return standalone.spec(name)
    return spec


def _ask(names: list[str], source: str) -> None:
    """Ask for each value this Python does not have yet, hidden as it is typed; set it here only."""
    for env in names:
        if os.environ.get(env):
            continue
        value = getpass.getpass(f"{env} ({source}, kept for this session only): ")
        if not value:
            raise ValueError(f"{env} was left empty.")
        os.environ[env] = value


def blade(name: str) -> Any:
    """Run a saved blade in this Python and return what it makes (its variable).

    A vault blade sets its environment variables and returns their names; a secret blade asks for any
    of its values this Python does not have yet (none on a second use) and returns their names; a
    snippet gives its text. Other blades first run the vault blades and ask for the secret-blade values
    their code needs.
    """
    spec = _spec(name)
    if spec["kind"] == "snippet":
        return str(spec["code"])  # text for a cell, with its <<name>> placeholders: nothing to run
    if spec["kind"] == "secret":
        _ask(list(spec["env_names"]), str(spec["name"]))
        return list(spec["env_names"])
    made = _made(spec)[0]
    if spec["kind"] != "vault":  # a connection's (the app counts only those), in a Workbench kernel only
        connection_use.report(str(spec["name"]), "connect")
    return _named(made, str(spec.get("table") or ""))


def register_table(name: str, value: Any) -> Any:
    """A blade's table under its own name (its header's `table = "..."`): in Jupyter, IPython or a Workbench
    kernel it is the variable `name`, so DuckDB SQL (%%sql, sab.sql) names it, the Workbench's Variables
    and the Open list show it, and Open as grid opens it by that name. Elsewhere it is only returned."""
    if not name or not is_table(value):
        return value
    module = sys.modules.get("IPython")
    get = getattr(module, "get_ipython", None) if module is not None else None
    shell = get() if callable(get) else None
    if shell is not None and isinstance(getattr(shell, "user_ns", None), dict):
        shell.user_ns[name] = value
    return value


def _named(made: Any, table: str) -> Any:
    """What a blade made, its table registered under `table`: a table at once, a function's table each
    time it is called."""
    if not table:
        return made
    if is_table(made):
        return register_table(table, made)
    if callable(made) and not isinstance(made, type):

        @functools.wraps(made)
        def table_of(*args: Any, **kwargs: Any) -> Any:
            return register_table(table, made(*args, **kwargs))

        return table_of
    return made


def _made(spec: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    """Run what the server gave for a blade: what it makes, and every name its code made."""
    label = str(spec["name"])
    try:
        for vault in spec.get("vaults", []):
            every = bool(vault.get("every"))
            run_vault(
                vault["code"], vault["variable"], vault["mapping"], vault["secrets"], vault["label"], every
            )
        for env, source in spec.get("typed", {}).items():
            _ask([env], source)
        if spec["kind"] == "vault":
            values = run_vault(
                spec["code"],
                spec["variable"],
                spec["vault_mapping"],
                spec["secrets"],
                label,
                bool(spec.get("vault_all")),
            )
            return sorted(values), {}
        python = spec.get("python")
        if python:
            # A connection from your own Python: its variables are set here as they are in the app
            # (the vaults above gave theirs), so its code runs unchanged.
            reads = env_reads(spec["code"], python.get("tables"), python.get("read"))
            set_variables(reads, python["set"], python["keyring"], spec["secrets"], label)
        return run_code(spec["code"], spec["variable"], spec["secrets"], label)
    except BladeRunError as error:
        if error.missing_module:
            raise ImportError(missing_module_hint(error.missing_module)) from None
        raise


def read(connection: str, table: str, schema: str = "", limit: int | None = None) -> Any:
    """A table's rows from a connection made of your own Python, by its Read a table box, run in this
    Python: `sab.read("Orders API", "orders")`. What that box returns (a DataFrame, a list of dicts...);
    `limit` rows, or every row."""
    spec = _spec(connection)
    command = (spec.get("python") or {}).get("read")
    if not command:
        raise ValueError(
            f"{spec['name']} has no Read a table box: sab.read is for a connection made of your own "
            "Python. For a database, use sab.sql(connection, query)."
        )
    _, names = _made(spec)
    try:
        rows, _ = read_table(names, command, schema, table, limit, spec["secrets"], str(spec["name"]))
    except BladeRunError as error:
        connection_use.report(str(spec["name"]), "read", ok=False)
        if error.missing_module:
            raise ImportError(missing_module_hint(error.missing_module)) from None
        raise
    connection_use.report(str(spec["name"]), "read")  # counted in a Workbench kernel only
    return rows


def python_tables(connection: str) -> tuple[list[tuple[str, str]], Callable[[str, str], Any]]:
    """A connection made of your own Python, connected once in this Python: the (schema, table) pairs
    its List the tables names, and a reader that runs its Read a table for one of them (every row).
    What a SQL cell on it reads (client/sql_cell.py)."""
    spec = _spec(connection)
    python = spec.get("python") or {}
    label = str(spec["name"])
    if not python.get("tables") or not python.get("read"):
        raise ValueError(
            f"{label} has no List the tables and Read a table boxes: fill them in its form (Connections)."
        )
    _, names = _made(spec)
    columns, rows = list_tables(names, str(python["tables"]), spec["secrets"], label)
    lowered = [c.strip().lower() for c in columns]
    table_at = next(i for i, c in enumerate(lowered) if c in ("table", "table_name"))
    schema_at = next((i for i, c in enumerate(lowered) if c in ("schema", "table_schema")), None)
    found = [
        ("" if schema_at is None or row[schema_at] is None else str(row[schema_at]), str(row[table_at]))
        for row in rows
    ]

    def reader(schema: str, table: str) -> Any:
        got, _ = read_table(names, str(python["read"]), schema, table, None, spec["secrets"], label)
        return got

    return list(dict.fromkeys(found)), reader
