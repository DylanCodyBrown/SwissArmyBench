"""DuckDB SQL that names a connection's tables (split from domain/connection_tables.py, which says what a
connection is and how a table is named through it; this module changes when DuckDB SQL handling does):

  [SQL]       the references whose first part is a connection's name found in sqlglot's tree (square
              brackets accepted as quoting for those names, rewritten before DuckDB sees them), and each
              pointed at the table it was read into (`__sab_conn_<n>`), keeping its own name as its alias
  [PUSHDOWN]  the work a query may send to the source with a reference (its columns, plain filters in the
              source's own SQL or structured, a safe LIMIT), so a query never runs on a cut table; a
              source's SELECT with its WHERE; the limit's words

Pure rules: standard library and sqlglot, no I/O.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlglot import exp

from swissarmybench.domain import catalogs
from swissarmybench.domain import connection_kinds as kinds
from swissarmybench.domain.connection_tables import ConnectionSqlError
from swissarmybench.domain.datasets import quote

__all__ = ["ConnectionSqlError", "Pushed", "Reference"]  # the error is the names' too: one class for both

PREFIX: str = "__sab_conn_"  # the table a reference was read into, in the query's DuckDB
MAX_REFERENCES: int = 20  # tables one query may read from connections


# ===== in SQL =====


@dataclass(frozen=True)
class Reference:
    """A table named through a connection in a query: the connection (as saved) and the rest of the name."""

    connection: str
    parts: tuple[str, ...]

    @property
    def key(self) -> tuple[str, ...]:
        return (self.connection.casefold(), *(p.casefold() for p in self.parts))


_SKIP = re.compile(r"'(?:[^']|'')*'|--[^\n]*|/\*.*?\*/", re.DOTALL)
# An unquoted name may end in a Delta table's @version or @time (orders@v12, orders@2026-11-01): quoted
# below when the chain is a connection's, so SQL reads it as one name.
_IDENT = (
    r'(?:\[[^\[\]\n]+\]|"(?:[^"]|"")+"|[A-Za-z_][A-Za-z0-9_$]*'
    r"(?:@(?:[vV]\d+|\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?)?)(?![\w:-]))?)"
)
_AT_NAME = re.compile(r"(\.\s*)([A-Za-z_][A-Za-z0-9_$]*@[A-Za-z0-9:-]+)")
_CHAIN = re.compile(rf"(?<![\w\].\"])({_IDENT})((?:\s*\.\s*{_IDENT})+)")


def _bare(identifier: str) -> str:
    if identifier.startswith("["):
        return identifier[1:-1]
    if identifier.startswith('"'):
        return identifier[1:-1].replace('""', '"')
    return identifier


def quote_brackets(text: str, names: Iterable[str]) -> str:
    """`[Finance Captive].[Sales model].Date` as `"Finance Captive"."Sales model".Date` (DuckDB reads
    square brackets as a list): only a dotted name whose first part is a connection's, outside quoted
    text and comments."""
    known = {n.casefold() for n in names}
    if ("[" not in text and "@" not in text) or not known:
        return text

    def chain(found: re.Match[str]) -> str:
        if _bare(found.group(1)).casefold() not in known:
            return found.group(0)
        rest = re.sub(r"\[([^\[\]\n]+)\]", lambda m: quote(m.group(1)), found.group(2))
        rest = _AT_NAME.sub(lambda m: m.group(1) + quote(m.group(2)), rest)
        first = found.group(1)
        return (quote(first[1:-1]) if first.startswith("[") else first) + rest

    out: list[str] = []
    at = 0
    for skipped in _SKIP.finditer(text):
        out.append(_CHAIN.sub(chain, text[at : skipped.start()]))
        out.append(skipped.group(0))
        at = skipped.end()
    out.append(_CHAIN.sub(chain, text[at:]))
    return "".join(out)


def _parse(text: str) -> Any:
    try:
        statements = [s for s in sqlglot.parse(text, read="duckdb") if s is not None]
    except sqlglot.errors.SqlglotError as error:
        first = str(error).strip().splitlines()[0] if str(error).strip() else "it does not parse"
        raise ConnectionSqlError(f"Could not parse the query: {first}") from error
    if len(statements) != 1:
        raise ConnectionSqlError("Run one statement at a time.")
    return statements[0]


def _named(table: exp.Table, names: Mapping[str, str]) -> Reference | None:
    if not isinstance(table.this, exp.Identifier) and not isinstance(table.this, exp.Dot):
        return None
    parts = [p.name for p in table.parts]
    if len(parts) < 2:
        return None
    saved = names.get(parts[0].casefold())
    return None if saved is None else Reference(saved, tuple(parts[1:]))


def references(text: str, names: Iterable[str]) -> list[Reference]:
    """The tables a query names through a connection (its first part a connection's name), each once, in
    order. Brackets already quoted (quote_brackets)."""
    by_name = {n.casefold(): n for n in names}
    if not by_name:
        return []
    found: dict[tuple[str, ...], Reference] = {}
    for table in _parse(text).find_all(exp.Table):
        ref = _named(table, by_name)
        if ref is not None:
            found.setdefault(ref.key, ref)
    if len(found) > MAX_REFERENCES:
        raise ConnectionSqlError(f"One query reads at most {MAX_REFERENCES} tables from connections.")
    return list(found.values())


def might_name(text: str, names: Iterable[str]) -> bool:
    """A cheap look before parsing: whether the text holds a connection's name followed by a dot."""
    lowered = text.casefold()
    return any(n.casefold() + "]." in lowered or n.casefold() + '".' in lowered or (
        n.isidentifier() and n.casefold() + "." in lowered
    ) for n in names)  # fmt: skip


def rewrite(text: str, names: Iterable[str], targets: Mapping[tuple[str, ...], str]) -> str:
    """The query with each connection's table pointed at the table it was read into, its own name kept
    as its alias (so `model_Report.amount` still means its column). In DuckDB's SQL."""
    by_name = {n.casefold(): n for n in names}
    root = _parse(text)
    for table in list(root.find_all(exp.Table)):
        ref = _named(table, by_name)
        if ref is None or ref.key not in targets:
            continue
        alias = table.args.get("alias")
        replaced = exp.Table(this=exp.to_identifier(targets[ref.key], quoted=True))
        replaced.set("alias", alias or exp.TableAlias(this=exp.to_identifier(ref.parts[-1], quoted=True)))
        table.replace(replaced)
    return str(root.sql(dialect="duckdb"))


def target_name(number: int) -> str:
    return f"{PREFIX}{number}"


# ===== work sent to the source (2026-11-17: a query never runs on a cut table) =====
#
# A connection's table named in a query is read whole, every row the query needs: never the connection's
# Rows to open (that limit is for opening a grid). What can be sent to the source is: the columns the
# query uses, and the WHERE conditions that touch only that table (a plain comparison of a column with
# a value), in the source's own SQL; DuckDB applies them again, so a source that compares text without
# case only reads more. A LIMIT goes too, only when nothing else in the query needs more rows.

# The lake and SharePoint kinds take their conditions as (column, op, value), applied by their own code;
# every other dialect's filter is written in its own SQL (catalogs.sqlglot_name), or not sent at all
# (each dialect's record says which: connection_kinds' filters).
_STRUCTURED: tuple[str, ...] = kinds.structured_filters()


def _filter_dialect(dialect: str) -> str | None:
    return "structured" if dialect in _STRUCTURED else catalogs.sqlglot_name(dialect)


_COMPARE = (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)
_DATES = {"DATE", "TIMESTAMP", "DATETIME"}


@dataclass(frozen=True)
class Pushed:
    """What a read sends to its source: the columns (none: every one), a WHERE in the source's SQL, the
    same as DuckDB wrote it (for the answer), and a LIMIT (None: every row)."""

    columns: tuple[str, ...] = ()
    where: str = ""
    said: str = ""
    limit: int | None = None
    # The same conditions as (column, op, value), for a source whose own code applies them (a lake's
    # DuckDB, SharePoint's $filter): =, <>, <, <=, >, >=, in, between, is null, is not null.
    filters: tuple[tuple[str, str, Any], ...] = ()

    def key(self) -> str:
        return f"{','.join(self.columns)}|{self.where}|{self.said}|{self.limit}"

    def to_json(self) -> dict[str, object]:
        return {"columns": list(self.columns), "filters": self.said, "limit": self.limit}


def _occurrences(root: Any, ref: Reference, names: Mapping[str, str]) -> list[exp.Table]:
    found = []
    for table in root.find_all(exp.Table):
        named = _named(table, names)
        if named is not None and named.key == ref.key:
            found.append(table)
    return found


def _alias(table: exp.Table, ref: Reference) -> str:
    return str(table.alias or ref.parts[-1]).casefold()


def _value(node: Any) -> str | None:
    """A plain value's kind: "text", "number", "date", or None (not a plain value)."""
    if isinstance(node, exp.Literal):
        return "text" if node.is_string else "number"
    if isinstance(node, exp.Neg) and isinstance(node.this, exp.Literal) and not node.this.is_string:
        return "number"
    if (
        isinstance(node, exp.Cast)
        and isinstance(node.this, exp.Literal)
        and node.this.is_string
        and node.to.this.name.upper() in _DATES
    ):
        return "date"
    return None


def _plain_condition(node: Any) -> bool:
    """A comparison of one column with plain values: col = 1, col IN ('a', 'b'), col BETWEEN 1 AND 3,
    col IS NULL. Text only with = and IN (a source that compares text without case, or orders it
    another way, would leave rows out for <, > or <>)."""
    if isinstance(node, exp.Paren):
        return _plain_condition(node.this)
    if isinstance(node, exp.Is):
        return isinstance(node.this, exp.Column) and isinstance(node.expression, exp.Null)
    if isinstance(node, exp.Not) and isinstance(node.this, exp.Is):
        return _plain_condition(node.this)
    if isinstance(node, exp.In):
        kinds = {_value(v) for v in node.expressions}
        return (
            isinstance(node.this, exp.Column)
            and bool(node.expressions)
            and None not in kinds
            and not node.args.get("query")
        )
    if isinstance(node, exp.Between):
        kinds = {_value(node.args.get("low")), _value(node.args.get("high"))}
        return isinstance(node.this, exp.Column) and None not in kinds and "text" not in kinds
    if isinstance(node, _COMPARE):
        left, right = node.this, node.expression
        if isinstance(right, exp.Column) and not isinstance(left, exp.Column):
            left, right = right, left
        kind = _value(right)
        if not isinstance(left, exp.Column) or kind is None:
            return False
        return kind != "text" or isinstance(node, exp.EQ)
    return False


def _conditions(root: exp.Select) -> list[Any]:
    where = root.args.get("where")
    if where is None:
        return []
    if isinstance(where.this, exp.And):
        return list(where.this.flatten())
    return [where.this]


def pushdown(text: str, names: Iterable[str], ref: Reference, known: Sequence[str], dialect: str) -> Pushed:
    """What a read of `ref` can send to its source, for this query (brackets already quoted): `known`,
    the table's columns as its catalog spells them (none: every column is read); `dialect`, the source's
    (catalogs.normalize_dialect's word; DAX and others: the columns at most)."""
    by_name = {n.casefold(): n for n in names}
    root = _parse(text)
    found = _occurrences(root, ref, by_name)
    if not found or not isinstance(root, exp.Select):
        return Pushed()
    tables = list(root.find_all(exp.Table))
    single = len(tables) == 1 and not root.args.get("joins") and not root.args.get("with_")
    aliases = {_alias(t, ref) for t in found}
    spelled = {c.casefold(): c for c in known}
    # The columns: every one the query names for this table (unqualified ones too, when they are its).
    wanted: list[str] = []
    every = not spelled
    for column in root.find_all(exp.Column):
        qualifier = column.table.casefold()
        if isinstance(column.this, exp.Star):
            every = every or qualifier in aliases
            continue
        if qualifier and qualifier not in aliases:
            continue
        if column.name.casefold() not in spelled:
            # A name the catalog does not know: its own, or a column alias. Read every column when it
            # could be this table's.
            every = every or bool(qualifier) or single
            continue
        wanted.append(spelled[column.name.casefold()])
    for join in root.args.get("joins") or []:
        # USING (region) names its columns as words, not columns; NATURAL names none: every column.
        if str(join.args.get("method") or "").upper() == "NATURAL" or "NATURAL" in join.sql().upper()[:20]:
            every = True
        for word in join.args.get("using") or []:
            name = getattr(word, "name", "") or str(word)
            if name.casefold() in spelled:
                wanted.append(spelled[name.casefold()])
    # Read in a subquery or a CTE (where its columns could be named any way): every column.
    direct = {id(j.this) for j in root.args.get("joins") or []}
    source = root.args.get("from_") or root.args.get("from")
    if source is not None:
        direct.add(id(source.this))
    every = every or any(id(t) not in direct for t in found)
    every = every or any(isinstance(e, exp.Star) for q in root.find_all(exp.Select) for e in q.expressions)
    if every:
        columns: tuple[str, ...] = ()
    else:
        columns = tuple(dict.fromkeys(wanted)) or (known[0],)
    target = _filter_dialect(dialect)
    if target is None or len(found) != 1 or not _filterable(root, found[0]):
        return Pushed(columns)
    alias = _alias(found[0], ref)
    conditions = _conditions(root)
    sent: list[Any] = []
    for condition in conditions:
        cols = list(condition.find_all(exp.Column))
        mine = all(c.table.casefold() == alias or (not c.table and single) for c in cols)
        if mine and cols and _plain_condition(condition) and all(c.name.casefold() in spelled for c in cols):
            sent.append(condition)
    said = " AND ".join(c.sql(dialect="duckdb") for c in sent)
    if target == "structured":
        structured = tuple(f for f in (_structured(c, spelled) for c in sent) if f is not None)
        limit = _safe_limit(root, single, len(structured) == len(conditions))
        return Pushed(columns, "", said, limit, structured)
    written: list[str] = []
    for condition in sent:
        copied = condition.copy()
        for c in list(copied.find_all(exp.Column)):
            c.replace(exp.column(exp.to_identifier(spelled[c.name.casefold()], quoted=True)))
        written.append(copied.sql(dialect=target))
    limit = _safe_limit(root, single, len(sent) == len(conditions))
    return Pushed(columns, " AND ".join(f"({w})" for w in written), said, limit)


def _plain_value(node: Any) -> Any:
    """A plain value as Python: a number, a text, a date as its text (2026-11-01)."""
    if isinstance(node, exp.Neg):
        return -_plain_value(node.this)
    if isinstance(node, exp.Cast):
        return str(node.this.this)
    if node.is_string:
        return str(node.this)
    text = str(node.this)
    return int(text) if text.lstrip("-").isdigit() else float(text)


def _structured(node: Any, spelled: Mapping[str, str]) -> tuple[str, str, Any] | None:
    """A plain condition (_plain_condition) as (column, op, value), its column as the catalog spells it."""
    if isinstance(node, exp.Paren):
        return _structured(node.this, spelled)
    if isinstance(node, exp.Not) and isinstance(node.this, exp.Is):
        return (spelled[node.this.this.name.casefold()], "is not null", None)
    if isinstance(node, exp.Is):
        return (spelled[node.this.name.casefold()], "is null", None)
    if isinstance(node, exp.In):
        return (spelled[node.this.name.casefold()], "in", [_plain_value(v) for v in node.expressions])
    if isinstance(node, exp.Between):
        low, high = _plain_value(node.args["low"]), _plain_value(node.args["high"])
        return (spelled[node.this.name.casefold()], "between", [low, high])
    ops = {exp.EQ: "=", exp.NEQ: "<>", exp.GT: ">", exp.GTE: ">=", exp.LT: "<", exp.LTE: "<="}
    flipped = {">": "<", ">=": "<=", "<": ">", "<=": ">="}
    op = ops.get(type(node))
    if op is None:
        return None
    left, right = node.this, node.expression
    if isinstance(right, exp.Column) and not isinstance(left, exp.Column):
        left, right, op = right, left, flipped.get(op, op)
    return (spelled[left.name.casefold()], op, _plain_value(right))


def _filterable(root: exp.Select, table: exp.Table) -> bool:
    """Whether the query's WHERE may be sent to this table's read: it is the FROM table with only inner or
    left joins after it, or an inner-joined one (a left or full join's other side keeps its rows)."""
    joins = list(root.args.get("joins") or [])
    sides = [str(j.args.get("side") or "").upper() for j in joins]
    kinds = [str(j.args.get("kind") or "").upper() for j in joins]
    if any(k not in ("", "INNER") for k in kinds):
        return False
    source = root.args.get("from_") or root.args.get("from")
    if source is not None and source.this is table:
        return all(side in ("", "LEFT") for side in sides)
    for join, side in zip(joins, sides, strict=True):
        if join.this is table:
            return side == "" and all(s in ("", "LEFT") for s in sides)
    return False


def _safe_limit(root: exp.Select, single: bool, all_sent: bool) -> int | None:
    """The query's LIMIT, when sending it reads every row the query needs: one table, no join, group,
    distinct, order, window or aggregate, and every condition sent."""
    limit = root.args.get("limit")
    if not single or not all_sent or limit is None or root.args.get("offset"):
        return None
    if any(root.args.get(k) for k in ("group", "having", "distinct", "order", "qualify")):
        return None
    if root.find(exp.Window, exp.AggFunc) is not None:
        return None
    value = limit.expression if isinstance(limit, exp.Limit) else None
    if isinstance(value, exp.Literal) and not value.is_string and str(value.this).isdigit():
        return int(value.this)
    return None


def with_filter(select: str, where: str) -> str:
    """A source SELECT (catalogs.select_sql) with its WHERE, before its LIMIT or FETCH FIRST."""
    if not where:
        return select
    for tail in ("\nLIMIT ", "\nFETCH FIRST "):
        if tail in select:
            head, _, rest = select.rpartition(tail)
            return f"{head}\nWHERE {where}{tail}{rest}"
    return f"{select}\nWHERE {where}"


def too_many(connection: str, table: str, count: int, limit: int, filtered: bool) -> str:
    """Why a table is not read into a query: more rows than the limit."""
    what = " with the filters sent" if filtered else ""
    return (
        f"[{connection}].{table} has {count:,} rows{what}: a query reads at most {limit:,} rows from a "
        "connection's table, never its first rows only. Add a WHERE that narrows it, or raise the limit: "
        "the SWISSARMYBENCH_MAX_QUERY_ROWS setting (an environment variable), then start the app again."
    )
