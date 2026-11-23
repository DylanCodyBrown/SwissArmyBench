"""What a connection is (the owner, 2026-11-17: "any connection ... exposes tables that we can write duckdb
against" / "that is the definition of a connection here"): something that lists its tables and reads one,
so DuckDB SQL can name them by the connection (`SELECT * FROM [Finance Captive].model_Report`).

  [CONTRACT]  every kind of connection lists its tables and reads one through the same two calls
              (services/connection_tables.py); this module says which way each kind does it (TABLE_KINDS)
              and which blades have no tables, and why (NO_TABLES): a key vault is not a connection
  [NAMES]     a table named through its connection: `connection.table`, `connection.schema.table`,
              `connection.database.schema.table`; a Power BI workspace's `connection.table` when one
              dataset holds it, else `connection.dataset.table`; a file or folder `connection.<sheet or
              file>`. Any case; an exact spelling wins a tie; a name two places share says which
  DuckDB SQL naming them (references found and rewritten, the work sent to the source) is
  domain/connection_sql.py's.

Pure rules: standard library and sqlglot, no I/O.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable, Sequence

from swissarmybench.domain import connection_kinds as kinds
from swissarmybench.domain import connections as rules
from swissarmybench.domain import web_calls
from swissarmybench.domain.connection_swap import Place

# How each kind of connection lists its tables and reads one (the contract's two calls), the kinds whose
# tables are named by their folders (a path), and the ones that have versions after @: each kind's own
# record says them (domain/connection_kinds.py); these are its views.
TABLE_KINDS: dict[str, tuple[str, str]] = kinds.tables_contract()
PATH_KINDS: frozenset[str] = kinds.path_kinds()
VERSIONED: frozenset[str] = kinds.versioned()
# Blades that expose no tables, so are not connections, with why.
NO_TABLES: dict[str, str] = {
    "vault": "not a connection: a source of secrets for variables",
    "api": "blades, not a connection: an API is one only through its web calls that return a table",
    "snippet": "not a connection: text for a cell",
    "analysis": "not a connection: an analysis run on a grid",
    "secret": "not a connection: a password",
    "other": "not a connection: code that makes a value (a function blade that returns a table could "
    "later be named in SQL too)",
}
_SHOWN: int = 12  # names an unknown table's answer lists


class ConnectionSqlError(ValueError):
    """A connection's table named in SQL that cannot be read as written; the message says what there is."""


def is_api(tags: Iterable[str], code: str) -> bool:
    """An API's own blade, the connection its tables are read through (Add API's blades version: the API
    blade is tagged `api`; its tables are exactly its web call blades with Return as table on). A web call
    blade is never one (it is tagged `web call` as well): it is a table of its API's, not a connection.
    An older API connection (Add API's API_<name>.py before the blades) is still one, by its code."""
    said = {str(t).casefold() for t in tags}
    if web_calls.TAG in said:
        return False
    return web_calls.API_TAG in said or ("spec_from_file_location(" in code and "API_" in code)


def tables_kind(
    kind: str,
    template: str | None,
    dialect: str | None = None,
    catalog_language: str | None = None,
    tags: Iterable[str] = (),
    code: str = "",
) -> str | None:
    """Which way a blade lists and reads its tables (a TABLE_KINDS key), or None: it has none."""
    connection = rules.connection_kind(kind, template)
    if connection == "database":
        # A dialect whose own record is a tables kind (a Power BI workspace, a lake, SharePoint) is that kind;
        # one with an older face (Dataverse's Web API) is that one unless its catalog is listed by SQL.
        own = kinds.engine(dialect) if dialect in kinds.dialects() else None
        if own is not None and own.unless_sql and catalog_language != "sql":
            return own.unless_sql
        return own.name if own is not None and own.tables else "database"
    if connection == "file":
        return "folder" if template == "folder" else "file"
    if connection == "python":
        return "api" if is_api(tags, code) else "python"
    return None


def no_tables_reason(kind: str, template: str | None) -> str:
    """Why a blade has no tables, in words."""
    connection = rules.connection_kind(kind, template)
    return NO_TABLES.get(connection or kind, NO_TABLES["other"])


# ===== a table's name through its connection =====

# A Delta table's version or time after its name: orders@v12, orders@2026-11-01, orders@2026-11-01T09:30.
AT = re.compile(r"@(?:[vV]\d+|\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?)?)$")


def path_parts(database: str, schema: str, table: str) -> list[str]:
    """A table's place as the parts its SQL name is made of: its folders, then its name (a workbook's
    sheet after its file)."""
    return [p for p in (database, *schema.split("/"), *table.split("/")) if p]


def split_at(name: str) -> tuple[str, str]:
    """A table's name and its @version or @time (empty when none): orders@v12 -> (orders, @v12)."""
    found = AT.search(name)
    return (name[: found.start()], found.group(0)) if found else (name, "")


def words(place: Place) -> str:
    return place.words()


def copy_name(connection: str, place: Place, kind: str, shared: Iterable[str] = ()) -> str:
    """How SQL names the table: `[Finance Captive].model_Report`, its dataset or schema too when the name
    alone would not say which (a table two datasets share; a database table outside the first schema)."""
    shared_names = {s.casefold() for s in shared}
    parts: list[str] = []
    found = kinds.get(kind)
    naming = found.naming if found is not None else "database"  # its record says how its tables are named
    if naming == "powerbi":
        parts = [place.schema, place.table] if place.table.casefold() in shared_names else [place.table]
    elif naming == "path":
        parts = path_parts(place.database, place.schema, place.table)
    elif naming in ("single", "file"):
        parts = [place.table]
    else:
        parts = [p for p in (place.database, place.schema, place.table) if p]
        if place.table.casefold() not in shared_names:
            parts = [place.table]
    return f"[{connection}]." + ".".join(_part(p) for p in parts)


def _part(name: str) -> str:
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else '"' + name.replace('"', '""') + '"'


def _equal(a: str, b: str, exact: bool) -> bool:
    return a == b if exact else a.casefold() == b.casefold()


def _matching(parts: Sequence[str], candidates: Sequence[Place], kind: str, exact: bool) -> list[Place]:
    """The candidates the parts after the connection's name can mean."""
    last = parts[-1]
    found = [c for c in candidates if _equal(c.table, last, exact)]
    if not found and kind == "folder":  # a folder's file by its name without its suffix: orders.csv as orders
        found = [c for c in candidates if "." in c.table and _equal(c.table.rsplit(".", 1)[0], last, exact)]
    if len(parts) == 1:
        return found
    if kind == "powerbi":
        return [c for c in found if len(parts) == 2 and _equal(c.schema, parts[0], exact)]
    if len(parts) == 2:
        # schema.table, or (a catalog spanning databases) database.table
        by_schema = [c for c in found if _equal(c.schema, parts[0], exact)]
        return by_schema or [c for c in found if _equal(c.database, parts[0], exact)]
    if len(parts) == 3:
        return [c for c in found if _equal(c.schema, parts[1], exact) and _equal(c.database, parts[0], exact)]
    return []


def _resolve_path(connection: str, kind: str, parts: Sequence[str], candidates: Sequence[Place]) -> Place:
    """A table named by its folders (a lake's, a library's): the parts are the end of its path (its last
    parts are enough when they name one table; the whole path, then an exact spelling, wins a tie), a
    file by its name with or without its suffix; a Delta table's @version or @time kept on its name."""
    *folders, last = parts
    name, at = split_at(last)
    if at and kind not in VERSIONED:
        raise ConnectionSqlError(f"{connection}'s tables have no versions: {last} names none.")
    wanted = [*folders, name]
    hits: list[tuple[bool, bool, Place]] = []
    for c in candidates:
        path = path_parts(c.database, c.schema, c.table)
        stem = [*path[:-1], path[-1].rsplit(".", 1)[0]] if "." in path[-1] else path
        for candidate in (path, stem):
            tail = candidate[-len(wanted) :]
            if len(candidate) >= len(wanted) and [p.casefold() for p in tail] == [
                w.casefold() for w in wanted
            ]:
                hits.append((len(candidate) == len(wanted), tail == wanted, c))
                break
    for keep in ((True, True), (True, None), (None, True), (None, None)):
        picked = [h[2] for h in hits if all(k is None or h[i] == k for i, k in enumerate(keep))]
        if len(picked) == 1:
            found = picked[0]
            return Place(found.database, found.schema, found.table + at) if at else found
    written = f"[{connection}]." + ".".join(parts)
    if hits:
        places = ", ".join(copy_name(connection, h[2], kind) for h in hits[:_SHOWN])
        raise ConnectionSqlError(f"{written} could be {places}: name its folders too.")
    if not candidates:
        raise ConnectionSqlError(f"{connection} lists no tables (its catalog is empty or not loaded).")
    paths = {".".join(path_parts(c.database, c.schema, c.table)) for c in candidates}
    names = sorted(paths, key=str.casefold)
    near = difflib.get_close_matches(".".join(wanted), names, n=3, cutoff=0.6)
    more = f" ... ({len(names)} in all)" if len(names) > _SHOWN else ""
    hint = f" Did you mean {', '.join(near)}?" if near else ""
    raise ConnectionSqlError(
        f"{connection} has no table {'.'.join(parts)}.{hint} It has: {', '.join(names[:_SHOWN])}{more}."
    )


def resolve(connection: str, kind: str, parts: Sequence[str], candidates: Sequence[Place]) -> Place:
    """The table `connection.<parts>` names among the connection's tables (any case; an exact spelling
    wins a tie). A name two places share says which; an unknown one says what there is."""
    if kind in PATH_KINDS and 0 < len(parts) <= 16:
        return _resolve_path(connection, kind, parts, candidates)
    written = f"[{connection}]." + ".".join(parts)
    if not parts or len(parts) > (2 if kind == "powerbi" else 3):
        shape = "[connection].[dataset].table" if kind == "powerbi" else "[connection].[schema].table"
        raise ConnectionSqlError(f"{written} is not a table's name: write {shape}.")
    found = _matching(parts, candidates, kind, exact=False)
    if len(found) > 1:
        found = _matching(parts, candidates, kind, exact=True) or found
    if len(found) == 1:
        return found[0]
    if found:
        if kind == "powerbi":
            sets = ", ".join(sorted({c.schema for c in found}, key=str.casefold))
            first = found[0]
            raise ConnectionSqlError(
                f"{parts[-1]} is in several datasets of {connection}: {sets}. Name the dataset: "
                f"[{connection}].{_part(first.schema)}.{_part(first.table)}."
            )
        places = ", ".join(c.words() for c in found[:_SHOWN])
        raise ConnectionSqlError(
            f"{written} could be {places}. Name its schema: [{connection}].<schema>.{_part(parts[-1])}."
        )
    names = sorted({c.table for c in candidates}, key=str.casefold)
    near = difflib.get_close_matches(parts[-1], names, n=3, cutoff=0.6)
    if not candidates:
        raise ConnectionSqlError(f"{connection} lists no tables (its catalog is empty or not loaded).")
    more = f" ... ({len(names)} in all)" if len(names) > _SHOWN else ""
    hint = f" Did you mean {', '.join(near)}?" if near else ""
    raise ConnectionSqlError(
        f"{connection} has no table {'.'.join(parts)}.{hint} It has: {', '.join(names[:_SHOWN])}{more}."
    )
