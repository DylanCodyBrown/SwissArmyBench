"""The Table pattern (the endpoint wizard's first: domain/api_patterns.py has the registry and the other
eight): the CRUD set over one sandbox table, appended to API.py, through the adapter (Plans/adapter.plan.md:
the per-source styles of 2026-11-21 went with the mock clients, 2026-11-22).

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

import ast
import io
import json
import keyword
import re
import sys
import tokenize
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


def py(value: Any, indent: int | None = None) -> str:
    """A value written as Python the way a formatter leaves it: double quotes; a long list of names one a
    line when `indent` (the line's own) is given."""
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, Mapping):
        return "{" + ", ".join(f"{py(k)}: {py(v)}" for k, v in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        flat = "[" + ", ".join(py(v) for v in value) + "]"
        if indent is None or len(flat) + indent <= 88:
            return flat
        pad = " " * (indent + 4)
        return "[\n" + "".join(f"{pad}{py(v)},\n" for v in value) + " " * indent + "]"
    return repr(value)


def _ident(text: str) -> str:
    made = re.sub(r"\W+", "_", text).strip("_").lower() or "table"
    if made[0].isdigit():
        made = "t_" + made
    return made + "_" if keyword.iskeyword(made) else made


def stem(table: str) -> str:
    """A table's part of its CRUD functions' names (list_<stem>)."""
    return _ident(table)


_SAB_API = ("ApiError", "Download", "connection", "download", "endpoint", "records")


def _used(block: str) -> set[str]:
    """The names a block of code reads (its annotations too)."""
    try:
        tree = ast.parse(block)
    except SyntaxError:
        return set(re.findall(r"[A-Za-z_]\w*", block))
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


def imports_missing(text: str, block: str = "") -> str:
    """The import lines a pattern's block needs that API.py does not have yet ("" when it has them): what
    the block reads of sab_api, TypedDict, and date or datetime (API.py would not start without them)."""
    imported = set(re.findall(r"^\s*from\s+[\w.]+\s+import\s+([^\n#]+)", text, re.M))
    names = {n.strip().split(" as ")[-1] for line in imported for n in line.strip("() ").split(",")}
    names |= set(re.findall(r"^import\s+(\w+)\s*$", text, re.M))  # a module by its own name
    used = _used(block) if block else {"TypedDict", "ApiError", "connection", "endpoint", "records"}
    lines = []
    if "TypedDict" in used and "TypedDict" not in names:
        lines.append("from typing import TypedDict  # noqa: E402")
    dates = [n for n in ("date", "datetime") if n in used and n not in names]
    if dates:
        lines.append(f"from datetime import {', '.join(dates)}  # noqa: E402")
    wanted = [n for n in _SAB_API if n in used and n not in names]
    if wanted:
        lines.append(f"from sab_api import {', '.join(wanted)}  # noqa: E402")
    return "\n".join(lines) + ("\n" if lines else "")


def fitted(text: str, block: str) -> str:
    """A block made to stand in this API.py: where the file imports the datetime module by its name
    (`import datetime`), the block's `date` and `datetime` are written `datetime.date` and
    `datetime.datetime` (importing the class would hide the module the file's own code uses). Only the
    code's own names: never a word in a string or a comment."""
    if not re.search(r"^import datetime\s*$", text, re.M) or re.search(
        r"^from datetime import [^\n]*\bdatetime\b", text, re.M
    ):
        return block
    spots: list[tuple[int, int]] = []
    before = ""
    try:
        for token in tokenize.generate_tokens(io.StringIO(block).readline):
            if token.type == tokenize.NAME and token.string in ("date", "datetime") and before != ".":
                spots.append(token.start)
            if token.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT, tokenize.INDENT):
                before = token.string
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return block
    lines = block.split("\n")
    for row, column in reversed(spots):
        lines[row - 1] = lines[row - 1][:column] + "datetime." + lines[row - 1][column:]
    return "\n".join(lines)


def with_imports(text: str, needs: str) -> tuple[str, str]:
    """API.py with the import lines a CRUD set needs written among its own imports (after the last one before
    its first function or class), so the file reads as one would write it and the linter stays quiet; and what
    is still to write before the set ("" then). No import of its own to stand beside: the lines go before the
    set, as they are."""
    if not needs:
        return text, ""
    lines = text.split("\n")
    rest = []
    for need in needs.strip("\n").split("\n"):  # a module API.py imports from already: its line takes them
        module, _, wanted = need.replace("  # noqa: E402", "").partition(" import ")
        at = next(
            (i for i, line in enumerate(lines) if re.fullmatch(rf"{re.escape(module)} import [\w, ]+", line)),
            -1,
        )
        if at < 0:
            rest.append(need)
            continue
        names = sorted(
            {n.strip() for n in (lines[at].partition(" import ")[2] + "," + wanted).split(",") if n.strip()}
        )
        lines[at] = f"{module} import {', '.join(names)}"
    text, needs = "\n".join(lines), "\n".join(rest) + ("\n" if rest else "")
    if not needs:
        return text, ""
    last = -1
    for i, line in enumerate(lines):
        if re.match(r"(def|class|async def|@)\b|@", line):
            break
        if re.match(r"(from\s+[\w.]+\s+import|import)\s", line) and not line.rstrip().endswith(("(", "\\")):
            last = i
    if last < 0:
        return text, needs
    added = [n.replace("  # noqa: E402", "") for n in needs.strip("\n").split("\n")]
    # A standard library module's line goes among the file's first import block (the standard library's, as
    # isort orders a file), in its place by module name; any other after the file's last import.
    standard = [n for n in added if _module(n).split(".")[0] in sys.stdlib_module_names]
    others = [n for n in added if n not in standard]
    lines = lines[: last + 1] + others + lines[last + 1 :]
    for line in standard:
        lines.insert(_place(lines, line), line)
    return "\n".join(lines), ""


_IMPORT = re.compile(r"(from\s+([\w.]+)\s+import|import\s+([\w.]+))\s?")


def _module(line: str) -> str:
    found = _IMPORT.match(line)
    return (found.group(2) or found.group(3) or "") if found else ""


def _place(lines: list[str], line: str) -> int:
    """Where a standard library import line goes: in the first block of top-level imports, plain `import x`
    lines first, then `from x import` lines by module name (isort's order); its end when none sorts after."""
    start = end = 0
    while True:  # the first block that is not `from __future__` alone (that one stands by itself)
        start = next((i for i in range(end, len(lines)) if _IMPORT.match(lines[i])), -1)
        if start < 0:
            return end
        end = start
        while end < len(lines) and _IMPORT.match(lines[end]):
            end += 1
        if any(_module(text) != "__future__" for text in lines[start:end]):
            break
    key = (line.startswith("from "), _module(line).casefold())
    for at in range(start, end):
        if (lines[at].startswith("from "), _module(lines[at]).casefold()) > key:
            return at
    return end


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
        raise ScaffoldError(f"The column {py(bad)} is not a Python name, so it cannot be a field of {model}.")
    head = [
        "",
        "",
        f"# ===== {table}: Table ({_style_words(source)}) =====",
        f"# pattern: table of {table}",
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
    return f"connection({py(source.connection)}) through the adapter"


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
    c = f"connection({py(source.connection)})"
    t = py(f"{source.schema}.{table}" if source.schema else table)
    return f'''{deco["list"]}
def list_{stem}(limit: int = 50, offset: int = 0) -> list[{model}]:
    """{table}: a page of its rows."""
    return records({c}.read({t}, sort=[[{py(key)}, "asc"]], limit=limit, offset=offset))


{deco["get"]}
def get_{stem}(key: {key_type}) -> {model}:
    """{table}: one row by {key}."""
    found = records({c}.read({t}, filters=[[{py(key)}, "=", key]], limit=1))
    if not found:
        raise ApiError(404, f"No {table} row has {key} {{key}}.")
    return found[0]


{deco["create"]}
def create_{stem}(row: {model}) -> {model}:
    """{table}: a new row from the body."""
    {c}.write({t}, [{{c: v for c, v in row.items() if c in {py(names)}}}])
    return row


{deco["update"]}
def update_{stem}(key: {key_type}, row: {model}) -> {model}:
    """{table}: the body's columns set on one row."""
    changes = {{c: v for c, v in row.items() if c in {py(names)} and c != {py(key)}}}
    if not changes:
        raise ApiError(422, "Send at least one column to change.")
    done = {c}.write({t}, [changes | {{{py(key)}: key}}], key=[{py(key)}], mode="update")
    if not done.updated:
        raise ApiError(404, f"No {table} row has {key} {{key}}.")
    return get_{stem}(key)


{deco["delete"]}
def delete_{stem}(key: {key_type}) -> None:
    """{table}: one row gone."""
    done = {c}.write({t}, [{{{py(key)}: key}}], key=[{py(key)}], mode="delete")
    if not done.deleted:
        raise ApiError(404, f"No {table} row has {key} {{key}}.")
'''
