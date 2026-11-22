"""New endpoint from a table: the CRUD set over one sandbox table, appended to API.py, through the adapter
(Plans/adapter.plan.md: the per-source styles of 2026-11-21 went with the mock clients, 2026-11-22).

  list    GET    /<table>?limit=&offset=      its rows, a page at a time (the API table widget pages with
  them)
  get     GET    /<table>/{key}               one row by its key (404 when there is none)
  create  POST   /<table>                     a row from the body (its model: a TypedDict of the columns)
  update  PUT    /<table>/{key}               the body's columns set on that row
  delete  DELETE /<table>/{key}               that row

One style for every source: connection(name).read(...) and .write(...), the adapter's calls, so the set runs
on the sandbox here and on the real connection (DuckDB, any SQL database, Dataverse, SharePoint) in an export.
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


def chosen_key(columns: Sequence[Mapping[str, Any]], key: str | None = None) -> str:
    """The CRUD set's key: the one asked for, else the table's own key's first column, else its first column."""
    names = [str(c["name"]) for c in columns]
    return key or next((str(c["name"]) for c in columns if c.get("key")), None) or (names[0] if names else "")


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
    chosen = chosen_key(columns, key)
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
        return 'connection("Sandbox") through the adapter'
    return f"connection({source.connection!r}) through the adapter"


def _decorators(path: str) -> dict[str, str]:
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
    """One style for every source: the adapter's read and write on connection(name), so the same code runs
    on the sandbox here and on the real connection in an export."""
    deco = _decorators(path)
    c = f"connection({source.connection!r})"
    t = repr(f"{source.schema}.{table}" if source.schema else table)
    return f'''{deco["list"]}
def list_{stem}(limit: int = 50, offset: int = 0) -> list[{model}]:
    """{table}: a page of its rows."""
    return records({c}.read({t}, sort=[[{key!r}, "asc"]], limit=limit, offset=offset))


{deco["get"]}
def get_{stem}(key: {key_type}) -> {model}:
    """{table}: one row by {key}."""
    found = records({c}.read({t}, filters=[[{key!r}, "=", key]], limit=1))
    if not found:
        raise ApiError(404, f"No {table} row has {key} {{key}}.")
    return found[0]


{deco["create"]}
def create_{stem}(row: {model}) -> {model}:
    """{table}: a new row from the body."""
    {c}.write({t}, [{{c: v for c, v in row.items() if c in {names!r}}}])
    return row


{deco["update"]}
def update_{stem}(key: {key_type}, row: {model}) -> {model}:
    """{table}: the body's columns set on one row."""
    changes = {{c: v for c, v in row.items() if c in {names!r} and c != {key!r}}}
    if not changes:
        raise ApiError(422, "Send at least one column to change.")
    done = {c}.write({t}, [changes | {{{key!r}: key}}], key=[{key!r}], mode="update")
    if not done.updated:
        raise ApiError(404, f"No {table} row has {key} {{key}}.")
    return get_{stem}(key)


{deco["delete"]}
def delete_{stem}(key: {key_type}) -> None:
    """{table}: one row gone."""
    done = {c}.write({t}, [{{{key!r}: key}}], key=[{key!r}], mode="delete")
    if not done.deleted:
        raise ApiError(404, f"No {table} row has {key} {{key}}.")
'''
