"""The Environment (the owner, 2026-11-21/22; Plans/environment.plan.md): everything the project holds on one
page, a tab for each kind: Tables, Variables (what the code makes), Structures, Settings and secrets,
Libraries.

The rules here, no I/O:

  items      one row's shape for every kind (`Item`): the page's, the Workbench's pane's and the agent's
  used in    every place in the app that uses a thing, each a link that goes there (`Used`): the grids
             showing a table (a grid is a view, never a copy), notebook and script cells by number, canvas
             widgets, API.py endpoints, analyses on the Analyze board, relationships in the ERD, tables
             made from it
  search     one search over every tab, by the Data Explorer's matching (domain/explorer.py: any case, by
             parts);
             each tab's count, and whether a row matched itself or inside (a column, a path, an item)
  libraries  requirements.txt read and written (Pin: name==version; Unpin; a library added or taken out), a
             library's name as pip compares it, what it is for, where it is imported, whether a newer one
             exists
  clear      Clear…'s ticks and what each would take
  insert     what a row is inserted into code as

Names, types, sizes and short looks only; a secret's value is never in an item (`masked`).
"""

from __future__ import annotations

import io
import json
import re
import tokenize
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain import explorer
from swissarmybench.domain.cell_facts import modules as imported_modules
from swissarmybench.domain.packages import pip_name, provided
from swissarmybench.domain.updates import try_version

KINDS: tuple[str, ...] = ("table", "variable", "structure", "setting", "library")
TABS: dict[str, str] = {
    "table": "Tables",
    "variable": "Variables",
    "structure": "Structures",
    "setting": "Settings and secrets",
    "library": "Libraries",
}
# Each tab's own columns, as the page's headings (the first is always Name).
COLUMNS: dict[str, tuple[str, ...]] = {
    "table": ("Name", "Rows by columns", "Columns", "Grids", "Used in", "From"),
    "variable": ("Name", "Type", "Value", "Used in", "From"),
    "structure": ("Name", "Format", "Size", "Paths", "Used in", "File"),
    "setting": ("Name", "Kind", "Value", "Comes from", "Used in"),
    "library": ("Name", "Pinned", "Version", "What it is for", "Imported in"),
}
MASK = "••••••••"
MAX_KIDS: int = 200
MAX_LOOK: int = 200
ACTIONS: tuple[str, ...] = (
    "list",
    "show",
    "libraries",
    "open",
    "rename",
    "keep",
    "insert",
    "remove",
    "clear",
    "install",
    "update",
    "pin",
)


class EnvironmentRuleError(ValueError):
    """A request the Environment cannot take, in one sentence."""


# ===== a row =====


@dataclass(frozen=True)
class Used:
    """One place that uses a thing: its kind (grid, cell, widget, endpoint, analysis, table, erd,
    connection, settings), its words, and where a click goes."""

    kind: str
    words: str
    link: Mapping[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "words": self.words, "link": dict(self.link)}


@dataclass
class Item:
    kind: str
    name: str
    type: str = ""  # in plain words
    size: str = ""
    value: str = ""  # a short look: column names, a value's start, a path; a secret's is MASK
    origin: str = ""  # From / File / Comes from
    sub: str | None = None  # sandbox (a table), secret or vault (a setting)
    tags: tuple[str, ...] = ()  # Keep, In Python
    grids: tuple[Mapping[str, Any], ...] = ()  # a table's views: {"id", "steps"}
    used: tuple[Used, ...] = ()
    kids: tuple[tuple[str, str, str], ...] = ()  # what the row unfolds to: (name, type, a short look)
    more: Mapping[str, Any] = field(default_factory=dict)  # its kind's own facts (rows, version, pinned...)

    @property
    def id(self) -> str:
        return f"{self.kind}:{self.name}"

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "type": self.type,
            "size": self.size,
            "value": self.value,
            "from": self.origin,
            "sub": self.sub,
            "tags": list(self.tags),
            "grids": [dict(g) for g in self.grids],
            "used": [u.to_json() for u in self.used],
            "kids": [list(k) for k in self.kids[:MAX_KIDS]],
            "more_kids": max(0, len(self.kids) - MAX_KIDS),
        } | dict(self.more)


def item_id(kind: Any, name: Any) -> tuple[str, str]:
    """A row named by the agent or the page: ("table", "orders"), from kind and name or "table:orders"."""
    if isinstance(name, str) and kind is None and ":" in name:
        kind, _, name = name.partition(":")
    if kind not in KINDS:
        raise EnvironmentRuleError(f"kind is one of: {', '.join(KINDS)}.")
    if not isinstance(name, str) or not name.strip():
        raise EnvironmentRuleError("name is the row's name, as the list shows it.")
    return str(kind), name.strip()


def count(n: int, word: str, many: str | None = None) -> str:
    return f"{n:,} {word if n == 1 else many or word + 's'}"


def short(text: str, limit: int = MAX_LOOK) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def columns_look(names: Sequence[str], shown: int = 4) -> str:
    """A table's short look: its first column names and how many more ("order_id, amount, +5")."""
    more = len(names) - shown
    return ", ".join(names[:shown]) + (f", +{more}" if more > 0 else "")


def table_size(rows: int | None, columns: int | None) -> str:
    left = "?" if rows is None else f"{rows:,}"
    return f"{left} \u00d7 {'?' if columns is None else columns}"


def bytes_words(size: int) -> str:
    for unit, step in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if size >= step:
            return f"{size / step:,.0f} {unit}"
    return f"{size} bytes"


TYPE_WORDS: dict[str, str] = {
    "int": "Whole number",
    "float": "Number",
    "str": "Text",
    "bool": "Yes / no",
    "list": "List",
    "tuple": "List",
    "dict": "Dictionary",
    "set": "Set",
    "frozenset": "Set",
    "date": "Date",
    "datetime": "Date and time",
    "Timestamp": "Date and time",
    "time": "Time",
    "Decimal": "Number",
    "NoneType": "Nothing",
    "bytes": "Bytes",
    "DataFrame": "Table",
    "Table": "Table",
    "DuckDBPyRelation": "Table",
    "Series": "Series",
    "ndarray": "Array",
    "Path": "Path",
    "PosixPath": "Path",
    "WindowsPath": "Path",
}
TABLE_KIND_WORDS: dict[str, str] = {
    "dataframe": "pandas table",
    "polars": "Polars table",
    "arrow": "Arrow table",
    "relation": "DuckDB relation",
    "table": "DuckDB table",
}


def type_words(python_type: str) -> str:
    """A Python value's type in plain words (its last name when the table does not know it)."""
    last = python_type.rsplit(".", 1)[-1]
    return TYPE_WORDS.get(last, last)


# ===== used in =====

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def words_in(text: str) -> set[str]:
    return set(_WORD.findall(text))


def code_only(source: str) -> str:
    """Python code without its comments (a name in a comment uses nothing): a cell that starts with a cell
    magic (%%sql: the source's own language) and code Python cannot read yet are given back as written."""
    if source.lstrip().startswith("%%") or "#" not in source:
        return source
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, SyntaxError):
        return source
    return " ".join(t.string for t in tokens if t.type != tokenize.COMMENT)


@dataclass(frozen=True)
class Document:
    """A notebook's or a script's code, to look for names in: its cells by number (a script: one, None)."""

    path: str
    title: str
    cells: tuple[tuple[int | None, str], ...]


def _numbers(found: Sequence[int]) -> str:
    return ("cell " if len(found) == 1 else "cells ") + ", ".join(str(n) for n in found)


def cell_uses(
    documents: Iterable[Document], names: Iterable[str], fold: bool = False
) -> dict[str, list[Used]]:
    """Where each name stands as a word in the documents' code: one entry a document ("data.ipynb · cells
    4, 6"; a script by its name), its link the first cell. `fold`: in any case (a table's name in SQL)."""
    wanted = {(n.casefold() if fold else n): n for n in names}
    found: dict[str, list[Used]] = {}
    for document in documents:
        hits: dict[str, list[int | None]] = {}
        for number, source in document.cells:
            for word in words_in(code_only(source)):
                name = wanted.get(word.casefold() if fold else word)
                if name is not None:
                    hits.setdefault(name, []).append(number)
        for name, cells in hits.items():
            numbers = sorted({n for n in cells if n is not None})
            words = document.title + (f" · {_numbers(numbers)}" if numbers else "")
            link: dict[str, Any] = {"to": "document", "path": document.path}
            if numbers:
                link["cell"] = numbers[0]
            found.setdefault(name, []).append(Used("cell", words, link))
    return found


def canvas_uses(canvases: Iterable[tuple[str, str]], names: Iterable[str]) -> dict[str, list[Used]]:
    """The canvas widgets whose values or wires name a table or a variable: "Canvas · <page> · <widget>".
    `canvases`: (the canvas's name, its file's text); one that does not read is skipped."""
    wanted = set(names)
    found: dict[str, list[Used]] = {}

    def strings(node: Any) -> Iterable[str]:
        if isinstance(node, str):
            yield node
        elif isinstance(node, dict):
            for value in node.values():
                yield from strings(value)
        elif isinstance(node, list):
            for value in node:
                yield from strings(value)

    def walk(canvas: str, page: str, node: Any) -> None:
        if not isinstance(node, dict):
            return
        if node.get("kind") == "widget":
            said: set[str] = set()
            for text in strings([node.get("values"), node.get("wires")]):
                said |= words_in(text) | {text}
            for name in sorted(wanted & said):
                words = f"Canvas · {page} · {node.get('widget') or 'widget'}"
                link = {"to": "canvas", "canvas": canvas, "page": page, "item": node.get("id")}
                found.setdefault(name, []).append(Used("widget", words, link))
        for child in node.get("children") or []:
            walk(canvas, page, child)

    for canvas, text in canvases:
        try:
            pages = json.loads(text).get("pages", [])
        except (ValueError, AttributeError):
            continue
        for page in pages if isinstance(pages, list) else []:
            if isinstance(page, dict):
                for child in page.get("children") or []:
                    walk(canvas, str(page.get("name") or page.get("id") or ""), child)
    return found


def endpoint_uses(endpoints: Iterable[Any], names: Iterable[str], path: str = "") -> dict[str, list[Used]]:
    """The API.py endpoints (domain/local_api.py's Endpoint) whose SQL or connections name a table, in any
    case: "API.py · GET /orders"."""
    wanted = {n.casefold(): n for n in names}
    found: dict[str, list[Used]] = {}
    for endpoint in endpoints:
        said: set[str] = {str(c).casefold() for c in endpoint.connections}
        for sql in endpoint.sql:
            said |= {w.casefold() for w in words_in(str(sql.get("text", "")))}
        for key in sorted(said & set(wanted)):
            link = {"to": "document", "path": path, "line": endpoint.line}
            found.setdefault(wanted[key], []).append(
                Used("endpoint", f"API.py · {endpoint.method} {endpoint.path}", link)
            )
    return found


def analysis_uses(
    cards: Iterable[Mapping[str, Any]], table_of_grid: Mapping[str, str]
) -> dict[str, list[Used]]:
    """The Analyze board's cards drawn on a table (through its grid): "Analyze · <the card's title>"."""
    found: dict[str, list[Used]] = {}
    for card in cards:
        table = table_of_grid.get(str(card.get("grid") or "")) or card.get("dataset")
        if not isinstance(table, str) or not table:
            continue
        title = str(card.get("title") or card.get("kind") or "card")
        link = {"to": "analyze", "card": card.get("id")}
        found.setdefault(table, []).append(Used("analysis", f"Analyze · {short(title, 60)}", link))
    return found


def erd_uses(relationships: Iterable[Any]) -> dict[str, list[Used]]:
    """The ERD's relationships a table is an end of: "ERD · orders → customers"."""
    found: dict[str, list[Used]] = {}
    for r in relationships:
        used = Used("erd", f"ERD · {r.from_table} → {r.to_table}", {"to": "erd"})
        for table in dict.fromkeys((r.from_table, r.to_table)):
            found.setdefault(table, []).append(used)
    return found


def made_from(queries: Mapping[str, str | None]) -> dict[str, list[Used]]:
    """The tables made from a table: a table whose query names it ("monthly (made from it)")."""
    found: dict[str, list[Used]] = {}
    folded = {name.casefold(): name for name in queries}
    for name, query in queries.items():
        if not query:
            continue
        for word in sorted({w.casefold() for w in words_in(query)} & set(folded)):
            if folded[word] != name:
                link = {"to": "table", "name": name}
                found.setdefault(folded[word], []).append(Used("table", f"{name} (made from it)", link))
    return found


def grid_uses(grids: Iterable[Mapping[str, Any]]) -> list[Used]:
    """A table's grids, each a view of it: "orders (3 steps)"."""
    out = []
    for grid in grids:
        steps = int(grid.get("steps") or 0)
        words = str(grid.get("name") or grid.get("id")) + (f" ({count(steps, 'step')})" if steps else "")
        out.append(Used("grid", words, {"to": "grid", "grid": grid.get("id")}))
    return out


def merged(*found: Mapping[str, list[Used]]) -> dict[str, list[Used]]:
    out: dict[str, list[Used]] = {}
    for each in found:
        for name, used in each.items():
            out.setdefault(name, []).extend(used)
    return out


# ===== search: the Data Explorer's matching, over every tab =====


@dataclass(frozen=True)
class Match:
    own: bool  # the row itself matched (its name, type, look, from or a place that uses it)
    kids: tuple[int, ...]  # the rows inside that matched (a column, a path, an item)

    @property
    def any(self) -> bool:
        return self.own or bool(self.kids)


def _all_hit(words: Sequence[str], texts: Sequence[str]) -> bool:
    return all(any(explorer.hit(w, t) for t in texts) for w in words)


def match(item: Item, words: Sequence[str]) -> Match:
    """Whether a row matches the search's words: every word in the row's own texts, or (with the row's name
    as their path) in one of the rows inside it."""
    if not words:
        return Match(True, ())
    texts = [item.name, item.type, item.value, item.origin, *(u.words for u in item.used)]
    own = _all_hit(words, texts)
    kids = tuple(i for i, kid in enumerate(item.kids) if _all_hit(words, [*kid, item.name]))
    kids = tuple(i for i in kids if any(explorer.hit(w, t) for w in words for t in item.kids[i]))
    return Match(own, kids)


def searched(items: Sequence[Item], text: Any) -> tuple[list[tuple[Item, Match]], dict[str, int]]:
    """The rows that match, each with how, and each tab's count."""
    words = explorer.words_of(text) if isinstance(text, str) else []
    found = [(item, m) for item in items if (m := match(item, words)).any]
    counts = dict.fromkeys(KINDS, 0)
    for item, _ in found:
        counts[item.kind] += 1
    return found, counts


def also(counts: Mapping[str, int], tab: str) -> list[dict[str, Any]]:
    """The other tabs that match ("Also matches in Variables (1)")."""
    return [{"kind": k, "name": TABS[k], "count": n} for k, n in counts.items() if k != tab and n > 0]


# ===== libraries: requirements.txt =====

_REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*([^#;]*)")
_LIBRARY_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}(\[[A-Za-z0-9_,.-]+\])?")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9.!+_-]{0,63}")


def library_key(name: str) -> str:
    """A library's name as pip compares it (PEP 503): lower case, runs of - _ . one dash, no extras."""
    return re.sub(r"[-_.]+", "-", name.partition("[")[0].strip().lower())


def check_library(name: Any) -> str:
    if not isinstance(name, str) or not _LIBRARY_NAME.fullmatch(name.strip()):
        raise EnvironmentRuleError("Name the library as pip knows it, such as pandas or psycopg[binary].")
    return name.strip()


def check_version(version: Any) -> str:
    if not isinstance(version, str) or not _VERSION.fullmatch(version.strip()):
        raise EnvironmentRuleError("version is the library's version, such as 2.3.3.")
    return version.strip()


@dataclass(frozen=True)
class Requirement:
    name: str  # as written, with its extras
    spec: str  # "==1.4.2", ">=2", "" (any)
    line: int

    @property
    def key(self) -> str:
        return library_key(self.name)

    @property
    def pinned(self) -> str | None:
        """The version it is pinned at (name==version), else None."""
        found = re.fullmatch(r"==\s*([^,\s*]+)", self.spec)
        return found.group(1) if found else None


def requirements(text: str) -> list[Requirement]:
    """requirements.txt's libraries (comments, options and blank lines are not libraries)."""
    found = []
    for number, line in enumerate(text.splitlines()):
        if not line.strip() or line.lstrip().startswith(("#", "-")):
            continue
        got = _REQUIREMENT.match(line)
        if got:
            found.append(Requirement(got.group(1) + (got.group(2) or ""), got.group(3).strip(), number))
    return found


def _with_line(text: str, key: str, line: str | None) -> str:
    """requirements.txt with the library `key`'s line replaced (None: taken out); added at the end when it
    is not there. Every other line as it was; the same text when nothing changes."""
    lines = text.splitlines()
    at = next((r.line for r in requirements(text) if r.key == key), None)
    if at is None:
        if line is None:
            return text
        lines.append(line)
    elif line is None:
        del lines[at]
    else:
        comment = lines[at].partition("#")[2]
        lines[at] = line + (f"  #{comment}" if comment else "")
    return "\n".join(lines) + "\n" if lines else ""


def _written(text: str, key: str, fallback: str) -> str:
    return next((r.name for r in requirements(text) if r.key == key), fallback)


def with_pin(text: str, name: str, version: str) -> str:
    """Pin: the library kept at its version (`name==version`)."""
    key = library_key(name)
    return _with_line(text, key, f"{_written(text, key, name)}=={check_version(version)}")


def without_pin(text: str, name: str) -> str:
    """Unpin: the library by its name alone, so an update may move it."""
    key = library_key(name)
    return _with_line(text, key, _written(text, key, name))


def with_library(text: str, name: str) -> str:
    """A library added (as it is, when it is already there)."""
    key = library_key(name)
    if any(r.key == key for r in requirements(text)):
        return text
    return _with_line(text, key, name)


def without_library(text: str, name: str) -> str:
    return _with_line(text, library_key(name), None)


def newer(installed: str, latest: str | None) -> str | None:
    """The newer version to offer ("→ x.y"), or None: none known, the same, or older."""
    have, there = try_version(installed), try_version(latest)
    if have is None or there is None or not latest:
        return None
    return latest if there > have else None


# What a library is for, in a few words (the Libraries tab's column); one not known here says nothing.
PURPOSES: dict[str, str] = {
    "duckdb": "The table engine",
    "pyarrow": "Arrow tables",
    "pandas": "Tables in Python",
    "polars": "Tables in Python",
    "numpy": "Arrays and maths",
    "openpyxl": "Excel files",
    "xlrd": "Old Excel files",
    "xlsxwriter": "Excel files",
    "streamlit": "The canvas's apps",
    "plotly": "Charts",
    "matplotlib": "Charts",
    "seaborn": "Charts",
    "altair": "Charts",
    "scikit-learn": "Models",
    "scipy": "Statistics",
    "statsmodels": "Statistics",
    "mssql-python": "SQL Server driver",
    "python-tds": "Dataverse's SQL endpoint",
    "pyodbc": "ODBC driver",
    "psycopg": "PostgreSQL driver",
    "pymysql": "MySQL driver",
    "oracledb": "Oracle driver",
    "trino": "Trino driver",
    "snowflake-connector-python": "Snowflake driver",
    "sqlalchemy": "Databases, one way",
    "requests": "Web calls",
    "httpx": "Web calls",
    "ipykernel": "Runs your code",
    "jedi": "Code completion",
    "ruff": "Lint and format",
    "pyyaml": "YAML files",
    "fastapi": "Web APIs",
    "starlette": "Web APIs",
    "uvicorn": "Web server",
    "azure-functions": "Azure Functions",
    "swissarmybench": "This app's client",
}
# What an environment always has that nobody chose: left out of the list unless requirements.txt names it or
# code imports it.
PLUMBING: frozenset[str] = frozenset({"pip", "setuptools", "wheel", "distribute"})


def purpose(name: str) -> str:
    return PURPOSES.get(library_key(name), "")


def imported_in(documents: Iterable[Document]) -> dict[str, list[Used]]:
    """Where each library is imported, by its pip name's key: one entry a document, its cells by number.
    Code that does not parse imports nothing."""
    found: dict[str, list[Used]] = {}
    for document in documents:
        hits: dict[str, list[int | None]] = {}
        for number, source in document.cells:
            try:
                names = imported_modules(_parsed(source))
            except SyntaxError:
                continue
            for module in names:
                if not provided(module):
                    hits.setdefault(library_key(pip_name(module)[0]), []).append(number)
        for key, cells in hits.items():
            numbers = sorted({n for n in cells if n is not None})
            words = document.title + (f" · {_numbers(numbers)}" if numbers else "")
            link: dict[str, Any] = {"to": "document", "path": document.path}
            if numbers:
                link["cell"] = numbers[0]
            found.setdefault(key, []).append(Used("cell", words, link))
    return found


def _parsed(source: str) -> Any:
    import ast

    # A notebook cell's magics (%%sql, %time) are not Python: their lines are left out.
    lines = [line for line in source.splitlines() if not line.lstrip().startswith(("%", "!"))]
    return ast.parse("\n".join(lines))


def library_items(
    installed: Mapping[str, str],
    required: Sequence[Requirement],
    imports: Mapping[str, list[Used]],
    latest: Mapping[str, str] | None = None,
) -> list[Item]:
    """The Libraries tab's rows: what requirements.txt names and what code imports first-hand, with each
    one's version here (none: not installed), its pin, a newer version when one is known."""
    by_key = {r.key: r for r in required}
    names = {library_key(n): n for n in installed}
    shown = set(by_key) | {k for k in names if k not in PLUMBING and (k in imports or not by_key)}
    shown |= {k for k in imports if k in names}
    items = []
    for key in sorted(shown):
        requirement = by_key.get(key)
        name = requirement.name.partition("[")[0] if requirement else names.get(key, key)
        version = installed.get(names.get(key, ""), "")
        newest = newer(version, (latest or {}).get(key)) if version else None
        pinned = requirement.pinned if requirement else None
        items.append(
            Item(
                "library",
                name,
                type=version or "not installed",
                size=version,
                value=purpose(key),
                origin="requirements.txt" if requirement else "installed, not in requirements.txt",
                used=tuple(imports.get(key, ())),
                more={
                    "version": version,
                    "installed": bool(version),
                    "pinned": pinned is not None,
                    "pinned_at": pinned,
                    "latest": newest,
                    "required": requirement is not None,
                },
            )
        )
    return items


# ===== settings and secrets =====

SETTING_SOURCES: dict[str, str] = {
    "vault": "key vault",
    "value": "the library's variables.toml",
    "keyring": "this computer's keyring",
    "env": "this computer's environment",
    "missing": "not set on this computer",
}


def setting_item(variable: Mapping[str, Any], used: Sequence[Used]) -> Item:
    """One `${NAME}` setting as a row (services/variables.py's listing): a secret's value is MASK, a vault's
    never read; a plain value in plain sight."""
    source = str(variable.get("from") or "missing")
    secret = bool(variable.get("secret")) or source in ("vault", "keyring")
    is_set = bool(variable.get("set"))
    if secret:
        value = f"{MASK} (set)" if is_set else "not set"
    else:
        value = short(str(variable.get("value") or "")) if is_set else "not set"
    if source == "vault":
        # The vault and the secret's name, never a value (the Variables page's line, kept as it folded in).
        origin = f"key vault · {variable.get('vault') or ''} · {variable.get('vault_secret') or ''}"
        where = f"key vault {variable.get('vault') or ''}, entry {variable.get('vault_secret') or ''}"
    else:
        origin = SETTING_SOURCES.get(source, source)
        if source == "value" and variable.get("local"):
            origin = "this computer only · local/variables.toml"
        where = origin
    kids = [("comes from", "source", where)]
    kids += [("used by", u.kind, u.words) for u in used]
    if secret:
        kids.append(("value", "never shown here", "Show is yours, in the viewer"))
    return Item(
        "setting",
        str(variable.get("name") or ""),
        type="Secret" if secret else "Setting",
        value=value,
        origin=origin,
        sub="secret" if secret else None,
        used=tuple(used),
        kids=tuple(kids),
        more={
            "secret": secret,
            "set": is_set,
            "source": source,
            "editable": bool(variable.get("editable")),
            "renamable": bool(variable.get("renamable")),
            "showable": source == "keyring" and is_set,
        },
    )


def setting_uses(uses: Iterable[Mapping[str, Any]]) -> list[Used]:
    """A setting's uses (services/variables.py's) as places: a connection, a notebook's or a script's cell."""
    out = []
    for use in uses:
        kind, name = str(use.get("kind")), str(use.get("name"))
        if kind == "connection":
            # The connection and the box the setting fills (Warehouse · Password).
            how = str(use.get("how") or "")
            words = f"{name} · {how[:1].upper()}{how[1:]}" if how else name
            out.append(Used("connection", words, {"to": "connection", "name": name}))
        elif kind == "run_settings":
            out.append(
                Used("settings", f"Run settings · {name}", {"to": "document", "path": use.get("path")})
            )
        else:
            cell = use.get("cell")
            words = name + (f" · cell {cell}" if cell is not None else "")
            link = {"to": "document", "path": use.get("path"), "cell": cell, "line": use.get("line")}
            out.append(Used("cell", words, {k: v for k, v in link.items() if v is not None}))
    return out


# ===== clear =====

CLEAR: dict[str, str] = {
    "tables": "Tables not kept with the project",
    "variables": "Variables (deleted in Python)",
    "structures": "Open structures (their files stay)",
}


def clear_choice(sent: Any) -> list[str]:
    """Clear…'s ticks as sent: {"tables": true, "variables": true, "structures": false}."""
    if not isinstance(sent, dict) or not all(isinstance(sent.get(k, False), bool) for k in CLEAR):
        raise EnvironmentRuleError(
            'Send the ticks: {"tables": true, "variables": true, "structures": false}.'
        )
    chosen = [k for k in CLEAR if sent.get(k)]
    if not chosen:
        raise EnvironmentRuleError("Tick what to clear: tables, variables or structures.")
    return chosen


def clear_plan(items: Sequence[Item]) -> dict[str, list[str]]:
    """What each tick would take: the tables not kept (never a sandbox's), every variable, the open
    structures."""
    return {
        "tables": [i.name for i in items if i.kind == "table" and "Keep" not in i.tags and i.sub is None],
        "variables": [i.name for i in items if i.kind == "variable"],
        "structures": [i.name for i in items if i.kind == "structure" and i.more.get("open")],
    }


def clear_words(plan: Mapping[str, Sequence[str]], chosen: Sequence[str]) -> str:
    parts = [count(len(plan[k]), k[:-1]) for k in chosen if plan.get(k)]
    return "Clear " + (", ".join(parts) if parts else "nothing")


# ===== insert into code =====

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def insert_code(kind: str, name: str, import_line: str = "") -> dict[str, str]:
    """What a row is inserted into code as: Python for a Python cell, SQL where a table has one."""
    if kind == "table":
        if _IDENTIFIER.fullmatch(name):
            return explorer.grid_insert(name)
        select = f"SELECT * FROM {explorer.sql_identifier(name)}"  # noqa: S608 (code for the user's cell)
        return {"sql": select, "python": f"sab.table({explorer.py_string(name)})"}
    if kind == "variable":
        return {"python": name}
    if kind == "structure":
        return {"python": f"sab.structure({explorer.py_string(name)})"}
    if kind == "setting":
        return explorer.variable_insert(name) | {"text": "${" + name + "}"}
    module = library_key(name).replace("-", "_")
    return {"python": import_line or f"import {module}"}
