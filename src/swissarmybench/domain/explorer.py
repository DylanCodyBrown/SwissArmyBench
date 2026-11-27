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
  the browse    the Catalog page with nothing typed (the owner, 2026-11-17: "a standalone DATA rail icon and
                page"; the one place to browse tables): every connection with its status and its tables,
                grouped as its tree groups them (database, schema; a Power BI workspace's datasets), then
                the open tables with their columns, Structures' documents with their paths, the APIs'
                table-returning calls with their columns, and the blades whose result is a table. Names only
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain import sandbox as boxes

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
    browse: bool = False  # the Catalog page's browse: every source's children too (names, never a value)

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


def hit(word: str, name: str) -> bool:
    """Whether a search word is in a text: in any case, and with the separators taken out."""
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
    own = [w for w in words if hit(w, name)]
    if not own or any(not hit(w, name) and not any(hit(w, p) for p in path) for w in words):
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


def blade_table_insert(name: str, variable: str, table: str) -> dict[str, str]:
    """A blade's table by its own name: SQL names it; Python makes it (a function blade's, by a call:
    `sab.blade` registers what the call returns under the table's name)."""
    call = f"sab.blade({py_string(name)})"
    python = f"{variable} = {call}" if variable else call
    return {"sql": sql_identifier(table), "python": python}


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


# ===== the browse (the Catalog page with nothing typed) =====

BROWSE_TABLES: int = 500  # a group's tables drawn at once (the search finds the rest)
# The sections after the connections, in order.
SECTIONS: tuple[tuple[str, str], ...] = (
    ("open", "Open tables"),
    ("sandbox", "Sandbox"),
    ("structures", "Structures"),
    ("apis", "APIs"),
    ("blades", "Blades"),
    ("shared", "From the shared catalog"),
)
# Which filter chips show each part of the browse (none pressed: every part).
_SHOWN_BY: dict[str, frozenset[str]] = {
    "connections": frozenset({"connections", "tables", "columns"}),
    "open": frozenset({"tables", "columns"}),
    "sandbox": frozenset({"tables", "columns"}),
    "structures": frozenset({"structures"}),
    "apis": frozenset({"apis", "columns"}),
    "blades": frozenset({"blades"}),
    "shared": frozenset({"tables", "columns"}),
}
# The connections whose relationships come in: a Power BI dataset's own, SQL Server's foreign keys.
RELATIONSHIP_DIALECTS: frozenset[str] = frozenset({"powerbi", "sqlserver"})


def browse_query(kinds: Any = None, connection: Any = None) -> Query:
    """The browse as the page or the agent asks for it: the filter chips and the connection picker."""
    q = parse("", kinds, connection, None, MAX_LIMIT)
    return Query("", (), q.kinds, q.connection, None, MAX_LIMIT, browse=True)


def shows(part: str, query: Query) -> bool:
    """Whether a part of the browse (connections, open, structures, apis, blades) is shown."""
    return bool(_SHOWN_BY[part] & query.kinds)


def imports_relationships(tables_kind: str | None, dialect: str | None) -> bool:
    """Import its relationships: a Power BI workspace's datasets, a SQL Server database's foreign keys."""
    return tables_kind == "powerbi" or (dialect or "") in RELATIONSHIP_DIALECTS


def blade_is_table(blade: Mapping[str, Any]) -> bool:
    """A blade whose result is a table: one that names its table, else a function blade (kind other) that
    is not an API's web call (those are the APIs' section's)."""
    if blade.get("table"):
        return True
    kind = str(blade.get("blade_kind") or blade.get("kind") or "")
    return kind == "other" and not blade.get("web_call")


def catalog_table(connection: str, table: Mapping[str, Any]) -> Result:
    """A connection's table as the browse holds it (its tree's entry: database, schema, table, sql)."""
    place = {k: str(table.get(k) or "") for k in ("database", "schema", "table")}
    sql = str(table.get("sql") or sql_identifier(place["table"]))
    path = [p for p in (connection, place["database"], place["schema"]) if p]
    return Result(
        "tables",
        place["table"],
        path,
        connection=connection,
        sql=sql,
        icon="rows",
        detail=str(table.get("title") or ""),
        insert=table_insert(sql),
        more={"place": place, "catalog": connection, "source": "catalog"},
    )


def connection_node(
    listed: Mapping[str, Any], tree: Mapping[str, Any] | None, error: str | None = None
) -> dict[str, Any]:
    """A connection in the browse: its type, its status (its catalog's state), whether it imports
    relationships, and its tables in groups (each cut to BROWSE_TABLES, counted whole)."""
    name = str(listed["name"])
    kind = str(listed.get("tables_kind") or "")
    state: dict[str, Any] = dict((tree or {}).get("state") or {"state": "none"})
    if error:
        state = {"state": "failed", "error": error}
    groups = []
    total = 0
    for g in (tree or {}).get("groups") or []:
        tables = [catalog_table(name, t).to_json() for t in g.get("tables") or []]
        total += len(tables)
        groups.append(
            {
                "database": str(g.get("database") or ""),
                "schema": str(g.get("schema") or ""),
                "count": len(tables),
                "tables": tables[:BROWSE_TABLES],
            }
        )
    return {
        "name": name,
        "type": str(listed.get("type") or listed.get("connection") or ""),
        "tables_kind": kind,
        "group_icon": "diagram" if kind == "powerbi" else "folder",  # its groups: datasets, or schemas
        "group": str((tree or {}).get("group") or "schema"),
        "state": state,
        "loaded": bool(groups) or state.get("state") == "loaded",
        "count": total,
        "relationships": imports_relationships(kind, listed.get("dialect")),
        "needs_password": bool(listed.get("needs_password")),
        "groups": groups,
    }


def _nested(
    parents: Sequence[Result],
    children: Sequence[Result],
    parent_of: Callable[[Result], Any],
    key_of: Callable[[Result], Any] = lambda p: p.name,
) -> list[dict[str, Any]]:
    by: dict[str, list[dict[str, Any]]] = {}
    for c in children:
        by.setdefault(str(parent_of(c)), []).append(c.to_json())
    out = []
    for p in parents:
        item = p.to_json()
        item["children"] = by.get(str(key_of(p)), [])
        out.append(item)
    return out


def _by_name(r: Result) -> tuple[list[str], str]:
    return [p.casefold() for p in r.path], r.name.casefold()


def sandbox_order(results: Sequence[Result], sort: tuple[str, bool]) -> list[Result]:
    """The Sandbox's tables among `results` in the sandbox list's own order (domain/sandbox.py sort_tables:
    name, rows, source, created, last changed), each in a slot one of them held; everything else stays."""

    slots = [at for at, r in enumerate(results) if r.kind == "tables" and r.more.get("source") == "sandbox"]
    rows = [
        {**results[at].more, "name": results[at].more.get("table") or results[at].name, "_at": at}
        for at in slots
    ]
    out = list(results)
    for slot, row in zip(slots, boxes.sort_tables(rows, *sort), strict=True):
        out[slot] = results[int(row["_at"])]
    return out


def browse_sections(
    results: Sequence[Result], query: Query, sandbox_sort: tuple[str, bool] | None = None
) -> list[dict[str, Any]]:
    """The sections after the connections, from the providers' results (a browse query's: with their
    children): the open tables and their columns, Structures' documents and their paths, the APIs'
    table-returning calls and their columns, the blades whose result is a table."""
    rs = [
        r
        for r in results
        if query.connection is None or (r.connection and same_name(r.connection, query.connection))
    ]
    grids = [r for r in rs if r.kind == "tables" and r.more.get("source") == "grid"]
    boxed = [r for r in rs if r.kind == "tables" and r.more.get("source") == "sandbox"]
    boxed_columns = [r for r in rs if r.kind == "columns" and r.more.get("source") == "sandbox"]
    grid_columns = [r for r in rs if r.kind == "columns" and r.more.get("source") == "grid"]
    docs = [r for r in rs if r.kind == "structures" and r.more.get("pointer") == "$"]
    paths = [r for r in rs if r.kind == "structures" and r.more.get("pointer") != "$"]
    calls = [r for r in rs if r.kind == "apis"]
    call_columns = [r for r in rs if r.kind == "columns" and r.more.get("source") == "api"]
    blades = [r for r in rs if r.kind == "blades" and blade_is_table(r.more)]
    shared = [r for r in rs if r.kind == "tables" and r.more.get("source") == "shared"]
    shared_columns = [r for r in rs if r.kind == "columns" and r.more.get("source") == "shared"]
    items: dict[str, list[dict[str, Any]]] = {
        "open": _nested(sorted(grids, key=_by_name), grid_columns, lambda c: c.more.get("table")),
        "sandbox": _nested(
            sandbox_order(boxed, sandbox_sort) if sandbox_sort else sorted(boxed, key=_by_name),
            boxed_columns,
            lambda c: c.more.get("table"),
        ),
        "structures": _nested(sorted(docs, key=_by_name), paths, lambda c: c.path[0] if c.path else ""),
        "apis": _nested(sorted(calls, key=_by_name), call_columns, lambda c: c.more.get("table")),
        "blades": [r.to_json() for r in sorted(blades, key=_by_name)],
        "shared": _nested(
            sorted(shared, key=_by_name),
            shared_columns,
            lambda c: c.more.get("table"),
            lambda p: p.more["key"],
        ),
    }
    return [
        {"kind": kind, "label": label, "count": len(items[kind]), "items": items[kind]}
        for kind, label in SECTIONS
        if shows(kind, query) and items[kind]
    ]


def table_code(sql: str) -> dict[str, str]:
    """The code that reads a table, for the detail side: a SQL cell's and a Python cell's."""
    select = f"SELECT *\nFROM {sql}\nLIMIT 100"
    one_line = f"SELECT * FROM {sql} LIMIT 100"  # noqa: S608 (code for the user's cell, not run here)
    return {"sql": f"%%sql\n{select}", "python": f"df = sab.sql({py_string(one_line)})"}
