"""New endpoint from a table: the CRUD set over one sandbox table, appended to API.py in the source's own
style (the
owner, 2026-11-21: "New endpoint from a table writes the code in the source's own style (T-SQL for SQL Server,
OData/FetchXML for Dataverse, list calls for SharePoint)").

  list    GET    /<table>?limit=&offset=      its rows, a page at a time (the API table widget pages with
  them)
  get     GET    /<table>/{key}               one row by its key (404 when there is none)
  create  POST   /<table>                     a row from the body (its model: a TypedDict of the columns)
  update  PUT    /<table>/{key}               the body's columns set on that row
  delete  DELETE /<table>/{key}               that row

The style follows the client the table is mocked as: `connection("Sandbox")` DuckDB SQL; a DB-API database its
own
SQL and driver marks (LIMIT/OFFSET, or Oracle's FETCH); SQL Server T-SQL through the starter's cursor
(OFFSET ... FETCH, `?` marks given one by one); Dataverse rows() with an OData filter (reads only: the
Dataverse
client writes through the Write starters); SharePoint lists rows() with filters, create(), update(), delete().
Pure text: standard library only.
"""

from __future__ import annotations

import keyword
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from swissarmybench.domain import local_api as api_rules


class ScaffoldError(ValueError):
    """The CRUD set cannot be made as asked, in one sentence."""


@dataclass(frozen=True)
class Source:
    """How the table is reached: its client's kind and dialect, the connection's name, its schema there."""

    kind: str  # duckdb, database, dataverse, sharepoint
    connection: str
    dialect: str = "duckdb"
    schema: str = ""


def _ident(text: str) -> str:
    made = re.sub(r"\W+", "_", text).strip("_").lower() or "table"
    if made[0].isdigit():
        made = "t_" + made
    return made + "_" if keyword.iskeyword(made) else made


def stem(table: str) -> str:
    """A table's part of its CRUD functions' names (list_<stem>)."""
    return _ident(table)


_NEEDED = {"TypedDict": "from typing import TypedDict", "ApiError": "sab_api", "connection": "sab_api",
           "endpoint": "sab_api", "records": "sab_api"}  # fmt: skip


def imports_missing(text: str, block: str = "") -> str:
    """The import lines a CRUD set needs that API.py does not have yet ("" when it has them). `block`: the
    set's text: a date or datetime field needs its import too (API.py would not start without it)."""
    imported = set(re.findall(r"^\s*from\s+[\w.]+\s+import\s+([^\n#]+)", text, re.M))
    names = {n.strip().split(" as ")[-1] for line in imported for n in line.strip("() ").split(",")}
    lines = []
    if "TypedDict" not in names:
        lines.append("from typing import TypedDict  # noqa: E402")
    used = re.findall(r"^    \w+: (date|datetime)$", block, re.M)
    dates = [n for n in ("date", "datetime") if n in used and n not in names]
    if dates:
        lines.append(f"from datetime import {', '.join(dates)}  # noqa: E402")
    wanted = [n for n in ("ApiError", "connection", "endpoint", "records") if n not in names]
    if wanted:
        lines.append(f"from sab_api import {', '.join(wanted)}  # noqa: E402")
    return "\n".join(lines) + ("\n" if lines else "")


def with_imports(text: str, needs: str) -> tuple[str, str]:
    """API.py with the import lines a CRUD set needs written among its own imports (after the last one before
    its first function or class), so the file reads as one would write it and the linter stays quiet; and what
    is still to write before the set ("" then). No import of its own to stand beside: the lines go before the
    set, as they are."""
    if not needs:
        return text, ""
    lines = text.split("\n")
    last = -1
    for i, line in enumerate(lines):
        if re.match(r"(def|class|async def|@)\b|@", line):
            break
        if re.match(r"(from\s+[\w.]+\s+import|import)\s", line) and not line.rstrip().endswith(("(", "\\")):
            last = i
    if last < 0:
        return text, needs
    added = [n.replace("  # noqa: E402", "") for n in needs.strip("\n").split("\n")]
    return "\n".join(lines[: last + 1] + added + lines[last + 1 :]), ""


def model_name(table: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[^A-Za-z0-9]+", table) if part) + "Row"


def _q(name: str, dialect: str) -> str:
    if dialect in ("sqlserver", "dataverse"):
        return "[" + name.replace("]", "]]") + "]"
    if dialect == "mysql":
        return "`" + name.replace("`", "``") + "`"
    return '"' + name.replace('"', '""') + '"' if not re.fullmatch(r"[a-z_][a-z0-9_]*", name) else name


def _mark(dialect: str, n: int) -> str:
    """The driver's parameter mark for the n-th value (1-based)."""
    if dialect in ("postgres", "mysql", "snowflake"):
        return "%s"
    if dialect == "oracle":
        return f":{n}"
    return "?"


def crud(
    table: str,
    columns: Sequence[Mapping[str, Any]],
    source: Source,
    key: str | None = None,
    taken: Sequence[str] = (),
    paths: Sequence[str] = (),
) -> str:
    """The CRUD set's text, to append to API.py. `taken`: the function and class names API.py has; `paths`: its
    paths (a set that would answer one twice is refused)."""
    names = [str(c["name"]) for c in columns]
    if not names:
        raise ScaffoldError(f"{table} has no columns.")
    chosen = key or next((str(c["name"]) for c in columns if c.get("key")), None) or names[0]
    if chosen not in names:
        raise ScaffoldError(f"{table} has no column {chosen} to be its key.")
    stem = _ident(table)
    model = model_name(table)
    fns = [f"list_{stem}", f"get_{stem}", f"create_{stem}", f"update_{stem}", f"delete_{stem}"]
    clash = [n for n in [model, *fns] if n in taken]
    if clash:
        raise ScaffoldError(f"API.py has {clash[0]} already: rename it, or make this table's set by hand.")
    path = "/" + re.sub(r"[^A-Za-z0-9._~-]+", "-", table.lower()).strip("-")
    if path in paths or path + "/{key}" in paths:
        raise ScaffoldError(f"API.py answers {path} already.")
    types = api_rules.model_types(columns)
    key_type = types.get(chosen, "str")
    field_lines = [
        f"    {n}: {types[n]}" if n.isidentifier() and not keyword.iskeyword(n) else "" for n in names
    ]
    if not all(field_lines):
        bad = next(n for n, line in zip(names, field_lines, strict=True) if not line)
        raise ScaffoldError(f"The column {bad!r} is not a Python name, so it cannot be a field of {model}.")
    head = [
        "",
        "",
        f"# ===== {table}: {_style_words(source)} (New endpoint from a table) =====",
        "",
        "",
        f"class {model}(TypedDict, total=False):",
        *field_lines,
        "",
        "",
    ]
    body = _styled(table, names, chosen, key_type, source, stem, model, path)
    return "\n".join(head) + body


def _style_words(source: Source) -> str:
    if source.kind == "duckdb":
        return 'connection("Sandbox"), DuckDB SQL'
    if source.kind == "dataverse":
        return f"a mock of {source.connection}'s Dataverse client, OData reads"
    if source.kind == "sharepoint":
        return f"a mock of {source.connection}'s SharePoint lists client"
    if source.dialect == "sqlserver":
        return f"a mock of {source.connection}'s SQL Server client, T-SQL"
    return f"a mock of {source.connection}'s client, its own SQL"


def _decorators(path: str, stem: str) -> dict[str, str]:
    return {
        "list": f'@endpoint("GET", "{path}")',
        "get": f'@endpoint("GET", "{path}/{{key}}")',
        "create": f'@endpoint("POST", "{path}", status=201)',
        "update": f'@endpoint("PUT", "{path}/{{key}}")',
        "delete": f'@endpoint("DELETE", "{path}/{{key}}")',
    }


def _styled(
    table: str, names: list[str], key: str, key_type: str, source: Source, stem: str, model: str, path: str
) -> str:
    deco = _decorators(path, stem)
    c = f"connection({source.connection!r})"
    if source.kind == "dataverse":
        return f'''{deco["list"]}
def list_{stem}(limit: int = 50, offset: int = 0) -> list[{model}]:
    """{table}: a page of its rows."""
    rows, _ = {c}.rows({table!r}, limit=offset + limit)
    return rows[offset:]


{deco["get"]}
def get_{stem}(key: {key_type}) -> {model}:
    """{table}: one row by {key}."""
    value = f"'{{key}}'" if isinstance(key, str) else key
    rows, _ = {c}.rows({table!r}, filter=f"{key} eq {{value}}", limit=1)
    if not rows:
        raise ApiError(404, f"No {table} row has {key} {{key}}.")
    return rows[0]


# Writes to Dataverse go through the Write starters (write_dataverse), not its read client.
'''
    if source.kind == "sharepoint":
        return f'''{deco["list"]}
def list_{stem}(limit: int = 50, offset: int = 0) -> list[{model}]:
    """{table}: a page of its items."""
    rows, _ = {c}.rows({table!r}, limit=offset + limit)
    return rows.to_pylist()[offset:]


{deco["get"]}
def get_{stem}(key: {key_type}) -> {model}:
    """{table}: one item by {key}."""
    rows, _ = {c}.rows({table!r}, filters=[[{key!r}, "=", key]], limit=1)
    found = rows.to_pylist()
    if not found:
        raise ApiError(404, f"No {table} item has {key} {{key}}.")
    return found[0]


{deco["create"]}
def create_{stem}(row: {model}) -> {model}:
    """{table}: a new item from the body."""
    {c}.create({table!r}, [row])
    return row


{deco["update"]}
def update_{stem}(key: {key_type}, row: {model}) -> {model}:
    """{table}: the body's columns set on one item."""
    {c}.update({table!r}, [dict(row) | {{{key!r}: key}}], key={key!r})
    return get_{stem}(key)


{deco["delete"]}
def delete_{stem}(key: {key_type}) -> None:
    """{table}: one item gone."""
    ids = {c}.ids({table!r}, [key], key={key!r})
    {c}.delete({table!r}, [ids[key]])
'''
    dialect = "duckdb" if source.kind == "duckdb" else source.dialect or "duckdb"
    qualified = (_q(source.schema, dialect) + "." if source.schema else "") + _q(table, dialect)
    k = _q(key, dialect)
    listed = ", ".join(_q(n, dialect) for n in names)
    if dialect == "sqlserver":
        page = f"SELECT {listed} FROM {qualified} ORDER BY {k} OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        page_args = "offset, limit"
    elif dialect == "oracle":
        page = f"SELECT {listed} FROM {qualified} ORDER BY {k} OFFSET :1 ROWS FETCH NEXT :2 ROWS ONLY"
        page_args = "[offset, limit]"
    else:
        page = f"SELECT {listed} FROM {qualified} ORDER BY {k} LIMIT {_mark(dialect, 1)} OFFSET {_mark(dialect, 2)}"
        page_args = "[limit, offset]"
    one = f"SELECT {listed} FROM {qualified} WHERE {k} = {_mark(dialect, 1)}"
    delete = f"DELETE FROM {qualified} WHERE {k} = {_mark(dialect, 1)}"
    if dialect == "sqlserver":  # mssql-python's cursor takes each value as its own argument
        run = "cursor.execute({sql!r}, {args})"
        one_args, key_args = "key", "key"
    else:
        run = "cursor.execute({sql!r}, {args})"
        one_args = key_args = "[key]"
    open_cursor = f"cursor = {c}.cursor()"
    insert_note = "the body's columns, in their order"
    return f'''{deco["list"]}
def list_{stem}(limit: int = 50, offset: int = 0) -> list[{model}]:
    """{table}: a page of its rows."""
    {open_cursor}
    {run.format(sql=page, args=page_args)}
    return records(cursor)


{deco["get"]}
def get_{stem}(key: {key_type}) -> {model}:
    """{table}: one row by {key}."""
    {open_cursor}
    {run.format(sql=one, args=one_args)}
    found = records(cursor)
    if not found:
        raise ApiError(404, f"No {table} row has {key} {{key}}.")
    return found[0]


{deco["create"]}
def create_{stem}(row: {model}) -> {model}:
    """{table}: a new row from the body ({insert_note})."""
    {open_cursor}
    columns = [c for c in {names!r} if c in row]
    {_insert(qualified, dialect)}
    return row


{deco["update"]}
def update_{stem}(key: {key_type}, row: {model}) -> {model}:
    """{table}: the body's columns set on one row."""
    {open_cursor}
    columns = [c for c in {names!r} if c in row and c != {key!r}]
    if not columns:
        raise ApiError(422, "Send at least one column to change.")
    {_update(qualified, dialect, k)}
    if cursor.rowcount == 0:
        raise ApiError(404, f"No {table} row has {key} {{key}}.")
    return get_{stem}(key)


{deco["delete"]}
def delete_{stem}(key: {key_type}) -> None:
    """{table}: one row gone."""
    {open_cursor}
    {run.format(sql=delete, args=key_args)}
    if cursor.rowcount == 0:
        raise ApiError(404, f"No {table} row has {key} {{key}}.")
'''


def _quotes(dialect: str) -> tuple[str, str]:
    return {"sqlserver": ("[", "]"), "dataverse": ("[", "]"), "mysql": ("`", "`")}.get(dialect, ('"', '"'))


def _mark_code(dialect: str, index: str) -> str:
    """Code for the mark of value number `index` (0-based) in the source's driver style."""
    if dialect == "oracle":
        return f'":" + str({index} + 1)'
    return repr("%s" if dialect in ("postgres", "mysql", "snowflake") else "?")


def _insert(qualified: str, dialect: str) -> str:
    left, right = _quotes(dialect)
    values = "*[row[c] for c in columns]" if dialect == "sqlserver" else "[row[c] for c in columns]"
    return (
        f'names = ", ".join({left!r} + c + {right!r} for c in columns)\n'
        f'    marks = ", ".join({_mark_code(dialect, "i")} for i in range(len(columns)))\n'
        f'    cursor.execute("INSERT INTO {qualified} (" + names + ") VALUES (" + marks + ")", {values})'
    )


def _update(qualified: str, dialect: str, key: str) -> str:
    left, right = _quotes(dialect)
    values = (
        "*[row[c] for c in columns], key" if dialect == "sqlserver" else "[*[row[c] for c in columns], key]"
    )
    return (
        f'sets = ", ".join({left!r} + c + {right!r} + " = " + {_mark_code(dialect, "i")} '
        f"for i, c in enumerate(columns))\n"
        f"    last = {_mark_code(dialect, 'len(columns)')}\n"
        f'    cursor.execute("UPDATE {qualified} SET " + sets + " WHERE {key} = " + last, {values})'
    )
