"""The Data Explorer (the owner, 2026-11-17: "a pane called Data Explorer that allows us to quickly
search by column names, table name, connection to quickly find data"): one search over everything that
holds data. Pure rules, no I/O.

  the query     words, matched in any case and by parts: `cust` finds `customer_id` and `CustomerKey`;
                `customerid` finds `customer_id` too (the name with its separators taken out); several
                words may be spread over a result's path (`orders cust`: orders' customer_id), but one of
                them must be in the result's own name
  the results   each a kind (KINDS), a name, its path (connection > schema > table > column), a type for a
                column, the connection it belongs to, its SQL name for a table, and the code it is inserted
                as (a SQL cell's and a Python cell's). Names only: never a value, a row or a secret
  the answer    grouped by kind in KINDS' order, each group counted (all the matches) and cut to the limit;
                the connections whose catalog is not loaded offered (Load its catalog)
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# The kinds of result, in the order the groups are shown (the filter chips' too).
KINDS: tuple[str, ...] = ("connections", "tables", "columns", "structures", "apis", "variables", "blades")
LABELS: dict[str, str] = {
    "connections": "Connections",
    "tables": "Tables",
    "columns": "Columns",
    "structures": "Structures",
    "apis": "APIs",
    "variables": "Variables",
    "blades": "Blades",
}
MAX_TEXT: int = 200  # characters in a search
DEFAULT_LIMIT: int = 25  # results shown per group
MAX_LIMIT: int = 200

_PARTS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")
_SEPARATORS = re.compile(r"[^0-9a-z]+")
_PLAIN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class ExplorerError(ValueError):
    """A search that cannot be made (a kind that is not one, a search too long)."""


@dataclass(frozen=True)
class Query:
    text: str
    words: tuple[str, ...]
    kinds: frozenset[str]
    connection: str | None = None  # only what belongs to this connection (the picker)
    column: str | None = None  # Show tables with this column: the column's exact name, in any case
    limit: int = DEFAULT_LIMIT

    def wants(self, kind: str) -> bool:
        return kind in self.kinds

    @property
    def empty(self) -> bool:
        return not self.words and self.column is None


def parse(
    text: Any = "", kinds: Any = None, connection: Any = None, column: Any = None, limit: Any = None
) -> Query:
    """A search as the page or the agent sends it: the text, the kinds (a list or "a,b"; none: every
    kind), a connection's name, a column's exact name, and the results shown per group."""
    raw = "" if text is None else str(text)
    if len(raw) > MAX_TEXT:
        raise ExplorerError(f"A search is at most {MAX_TEXT} characters.")
    if kinds in (None, "", []):
        chosen = frozenset(KINDS)
    else:
        listed = kinds.split(",") if isinstance(kinds, str) else kinds
        if not isinstance(listed, list | tuple):
            raise ExplorerError("kinds is a list of kinds: " + ", ".join(KINDS) + ".")
        names = [str(k).strip().lower() for k in listed if str(k).strip()]
        unknown = [k for k in names if k not in KINDS]
        if unknown:
            raise ExplorerError(f"{unknown[0]!r} is not a kind. The kinds: {', '.join(KINDS)}.")
        chosen = frozenset(names) or frozenset(KINDS)
    picked = str(connection).strip() if connection not in (None, "") else None
    exact = str(column).strip() if column not in (None, "") else None
    if exact is not None and len(exact) > MAX_TEXT:
        raise ExplorerError(f"A column's name is at most {MAX_TEXT} characters.")
    try:
        count = DEFAULT_LIMIT if limit in (None, "") else int(limit)
    except (TypeError, ValueError):
        raise ExplorerError("limit is a number of results.") from None
    count = min(MAX_LIMIT, max(1, count))
    return Query(raw.strip(), tuple(words_of(raw)), chosen, picked, exact, count)


def words_of(text: str) -> list[str]:
    """The search's words, lower case (spaces between them; a word keeps its own dots and underscores)."""
    return [w for w in text.lower().split() if w]


def parts(name: str) -> list[str]:
    """A name's parts: `CustomerKey` -> customer, key; `customer_id` -> customer, id; `HTTPStatus2` ->
    http, status, 2."""
    return [p.lower() for p in _PARTS.findall(name)]


def folded(text: str) -> str:
    """Lower case with every separator taken out: `Customer_ID` -> customerid."""
    return _SEPARATORS.sub("", text.lower())


def _hit(word: str, name: str) -> bool:
    low = name.lower()
    if word in low:
        return True
    plain = folded(word)
    return bool(plain) and plain in folded(name)


def score(name: str, words: Sequence[str], path: Sequence[str] = ()) -> int | None:
    """How well a result matches (lower is better), or None when it does not: every word in its name or
    its path, at least one in its name. 0 its name exactly, 1 its name starts with a word, 2 one of its
    parts does, 3 a word is inside it."""
    if not words:
        return 3
    own = [w for w in words if _hit(w, name)]
    if not own or any(not _hit(w, name) and not any(_hit(w, p) for p in path) for w in words):
        return None
    low = name.lower()
    text = " ".join(words)
    if low == text or folded(name) == folded(text):
        return 0
    if any(low.startswith(w) or folded(name).startswith(folded(w)) for w in own):
        return 1
    name_parts = parts(name)
    if any(any(p.startswith(w) for p in name_parts) for w in own):
        return 2
    return 3


def same_name(a: str, b: str) -> bool:
    return a.casefold() == b.casefold()


# ===== a result =====


@dataclass
class Result:
    kind: str
    name: str
    path: list[str] = field(default_factory=list)  # what it is in, outermost first (not its own name)
    connection: str | None = None
    sql: str | None = None  # a table's name in DuckDB SQL ([Finance Captive].model_Report)
    type: str | None = None  # a column's type
    detail: str = ""  # a few words: rows, a kind, a source
    icon: str = ""
    insert: dict[str, str] = field(default_factory=dict)  # the code it goes into a cell as: sql, python
    more: dict[str, Any] = field(default_factory=dict)  # what its actions need (a grid, a place, a pointer)
    rank: int = 3

    def key(self) -> str:
        return "/".join([self.kind, self.connection or "", *self.path, self.name])

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "key": self.key(),
            "kind": self.kind,
            "name": self.name,
            "path": self.path,
            "connection": self.connection,
            "detail": self.detail,
            "icon": self.icon,
            "insert": self.insert,
        }
        if self.sql is not None:
            out["sql"] = self.sql
        if self.type is not None:
            out["type"] = self.type
        return out | self.more


def ranked(results: Iterable[Result], query: Query) -> list[Result]:
    """The results that match, each scored, in order: kind, then the best match, shorter names, names."""
    out: list[Result] = []
    for r in results:
        if r.kind not in query.kinds:
            continue
        if query.connection is not None and not (r.connection and same_name(r.connection, query.connection)):
            continue
        if query.column is not None:
            if r.kind != "columns" or not same_name(r.name, query.column):
                continue
            r.rank = 0
        else:
            found = score(r.name, query.words, r.path)
            if found is None:
                continue
            r.rank = found
        out.append(r)
    order = {k: i for i, k in enumerate(KINDS)}
    out.sort(
        key=lambda r: (order[r.kind], r.rank, len(r.name), r.name.casefold(), [p.casefold() for p in r.path])
    )
    return out


def grouped(
    results: Sequence[Result], query: Query, offers: Sequence[Mapping[str, Any]] = ()
) -> dict[str, Any]:
    """The answer: each kind's group (its label, every match counted, the first `limit`), the total, the
    connections offered for loading, and the search as understood."""
    seen: set[str] = set()
    unique = []
    for r in results:
        if r.key() not in seen:
            seen.add(r.key())
            unique.append(r)
    groups = []
    for kind in KINDS:
        found = [r for r in unique if r.kind == kind]
        if found:
            groups.append(
                {
                    "kind": kind,
                    "label": LABELS[kind],
                    "count": len(found),
                    "results": [r.to_json() for r in found[: query.limit]],
                }
            )
    return {
        "query": {
            "text": query.text,
            "kinds": [k for k in KINDS if k in query.kinds],
            "connection": query.connection,
            "column": query.column,
        },
        "groups": groups,
        "total": len(unique),
        "offers": [dict(o) for o in offers],
    }


# ===== the code a result goes into a cell as =====


def sql_identifier(name: str) -> str:
    """A name as DuckDB SQL writes it: as it is when plain, else in double quotes."""
    return name if _PLAIN.fullmatch(name) else '"' + name.replace('"', '""') + '"'


def py_string(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def table_insert(sql_name: str) -> dict[str, str]:
    """A connection's table: `SELECT * FROM [C].t` in a SQL cell, `sab.sql("SELECT ...")` in Python."""
    select = f"SELECT * FROM {sql_name}"  # noqa: S608 (code for the user's cell, not run here)
    return {"sql": select, "python": f"sab.sql({py_string(select)})"}


def grid_insert(variable: str) -> dict[str, str]:
    """An open table: its name in a SQL cell's DuckDB (the kernel's DataFrame), its variable in Python."""
    return {"sql": f"SELECT * FROM {sql_identifier(variable)}", "python": variable}  # noqa: S608


def column_insert(column: str, variable: str | None = None) -> dict[str, str]:
    """A column: its quoted name in SQL; in Python `orders["customer_id"]` for an open table's, else its
    name as a string."""
    python = f"{variable}[{py_string(column)}]" if variable else py_string(column)
    return {"sql": sql_identifier(column), "python": python}


def variable_insert(name: str) -> dict[str, str]:
    """A variable: what Python reads it as (its value is the server's environment's, never in the code)."""
    return {"python": f"os.environ[{py_string(name)}]"}


def blade_insert(name: str, variable: str | None, kind: str, signature: str | None = None) -> dict[str, str]:
    """A blade: its call. A vault or a secret sets environment variables (no value to keep); a function
    blade's signature is called as written."""
    if signature:
        return {"python": signature}
    call = f"sab.blade({py_string(name)})"
    if kind in ("vault", "secret") or not variable:
        return {"python": call}
    return {"python": f"{variable} = {call}"}


# ===== a structure's names and paths (Structures: JSON, YAML, XML, TOML) =====

MAX_STRUCTURE_PATHS: int = 2000  # paths one structure gives the search
_LIST_ITEMS: int = 20  # the items of a list walked for their keys (records share theirs)
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class StructurePath:
    """One key in a structure: `$.orders[].customer.id` (a list's items as `[]`), the parts of one place
    that has it (`["orders", 0, "customer", "id"]`, for Open at this node), its key, its value's type."""

    pointer: str
    parts: tuple[str | int, ...]
    key: str
    type: str


def _type_of(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "list"
    return "null" if value is None else type(value).__name__


def _key_text(key: str) -> str:
    return f".{key}" if _NAME.fullmatch(key) else "[" + json.dumps(key, ensure_ascii=False) + "]"


def structure_paths(value: Any, limit: int = MAX_STRUCTURE_PATHS) -> list[StructurePath]:
    """Every key of a structure once, by its pointer (a list's items are one: `[]`), in the order met."""
    seen: dict[str, StructurePath] = {}

    def walk(node: Any, pointer: str, parts: tuple[str | int, ...]) -> None:
        if len(seen) >= limit:
            return
        if isinstance(node, dict):
            for key, child in node.items():
                text = str(key)
                at = pointer + _key_text(text)
                if at not in seen and len(seen) < limit:
                    seen[at] = StructurePath(at, (*parts, text), text, _type_of(child))
                walk(child, at, (*parts, text))
        elif isinstance(node, list):
            for index, child in enumerate(node[:_LIST_ITEMS]):
                walk(child, pointer + "[]", (*parts, index))

    walk(value, "$", ())
    return list(seen.values())


def parent_pointer(pointer: str) -> str:
    """`$.orders[].customer.id` -> `$.orders[].customer`; `$.orders` -> `$`."""
    at = max(pointer.rfind("."), pointer.rfind('["'))
    return pointer[:at] if at > 1 else "$"
