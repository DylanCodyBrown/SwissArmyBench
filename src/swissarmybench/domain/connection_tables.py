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
  [SQL]       the references whose first part is a connection's name found in sqlglot's tree (square
              brackets accepted as quoting for those names, rewritten before DuckDB sees them), and each
              pointed at the table it was read into (`__sab_conn_<n>`), keeping its own name as its alias

Pure rules: standard library and sqlglot, no I/O.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlglot import exp

from swissarmybench.domain import connections as rules
from swissarmybench.domain import dataverse, powerbi
from swissarmybench.domain.connection_swap import Place

# How each kind of connection lists its tables and reads one (the contract's two calls).
TABLE_KINDS: dict[str, tuple[str, str]] = {
    "database": (
        "its catalog (the connection's own query of its information schema)",
        "a SELECT in its own SQL (select_sql)",
    ),
    "powerbi": (
        "its datasets (the catalog's schemas), then each dataset's tables",
        "DAX on the table's dataset: EVALUATE 'Table'",
    ),
    "dataverse": (
        "its read-only SQL endpoint's own catalog (TDS, port 5558: INFORMATION_SCHEMA)",
        "a T-SQL SELECT on the SQL endpoint",
    ),
    "dataverse_web": (
        "its Web API's metadata (a connection saved before the SQL endpoint was the default)",
        "the Web API's read (switch it to the SQL endpoint on its card)",
    ),
    "python": ("its List the tables box", "its Read a table box"),
    "api": ("its web calls that return a table (the API's List the tables)", "the web call (Read a table)"),
    "file": ("the file itself: one table, or a workbook's sheets", "DuckDB's reader, or the sheet"),
    "folder": ("its files", "the file (a workbook's first sheet)"),
}
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
PREFIX: str = "__sab_conn_"  # the table a reference was read into, in the query's DuckDB
MAX_REFERENCES: int = 20  # tables one query may read from connections
_SHOWN: int = 12  # names an unknown table's answer lists


class ConnectionSqlError(ValueError):
    """A connection's table named in SQL that cannot be read as written; the message says what there is."""


def is_api(tags: Iterable[str], code: str) -> bool:
    """An Add API connection (its tables are the API's table-returning web calls). The one place that
    says which connections are APIs: the blades version of Add API changes only this."""
    return "api" in {str(t).casefold() for t in tags} or (
        "spec_from_file_location(" in code and "API_" in code
    )


def web_call_table(header: Mapping[str, object]) -> bool:
    """A web call blade that is one of its API's tables: its Return as table switch on (the blades
    version of Add API, 2026-11-17: "the gate for making it querable from DuckDB"). Nothing else of an
    API's is a table."""
    return header.get("kind") == "web_call" and header.get("return_as_table") is True


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
        if dialect == powerbi.DIALECT:
            return "powerbi"
        if dataverse.is_dataverse(dialect):
            return "dataverse" if catalog_language == "sql" else "dataverse_web"
        return "database"
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


def words(place: Place) -> str:
    return place.words()


def copy_name(connection: str, place: Place, kind: str, shared: Iterable[str] = ()) -> str:
    """How SQL names the table: `[Finance Captive].model_Report`, its dataset or schema too when the name
    alone would not say which (a table two datasets share; a database table outside the first schema)."""
    shared_names = {s.casefold() for s in shared}
    parts: list[str] = []
    if kind == "powerbi":
        parts = [place.schema, place.table] if place.table.casefold() in shared_names else [place.table]
    elif kind in ("file", "folder", "python", "api", "dataverse", "dataverse_web"):
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


def resolve(connection: str, kind: str, parts: Sequence[str], candidates: Sequence[Place]) -> Place:
    """The table `connection.<parts>` names among the connection's tables (any case; an exact spelling
    wins a tie). A name two places share says which; an unknown one says what there is."""
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
_IDENT = r'(?:\[[^\[\]\n]+\]|"(?:[^"]|"")+"|[A-Za-z_][A-Za-z0-9_$]*)'
_CHAIN = re.compile(rf"(?<![\w\].\"])({_IDENT})((?:\s*\.\s*{_IDENT})+)")


def _bare(identifier: str) -> str:
    if identifier.startswith("["):
        return identifier[1:-1]
    if identifier.startswith('"'):
        return identifier[1:-1].replace('""', '"')
    return identifier


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def quote_brackets(text: str, names: Iterable[str]) -> str:
    """`[Finance Captive].[Sales model].Date` as `"Finance Captive"."Sales model".Date` (DuckDB reads
    square brackets as a list): only a dotted name whose first part is a connection's, outside quoted
    text and comments."""
    known = {n.casefold() for n in names}
    if "[" not in text or not known:
        return text

    def chain(found: re.Match[str]) -> str:
        if _bare(found.group(1)).casefold() not in known:
            return found.group(0)
        rest = re.sub(r"\[([^\[\]\n]+)\]", lambda m: _quoted(m.group(1)), found.group(2))
        first = found.group(1)
        return (_quoted(first[1:-1]) if first.startswith("[") else first) + rest

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

# The dialects a filter is written in (sqlglot's names); any other is read without one.
_FILTER_DIALECTS: dict[str, str] = {
    "sqlserver": "tsql",
    "dataverse": "tsql",
    "postgres": "postgres",
    "mysql": "mysql",
    "sqlite": "sqlite",
    "duckdb": "duckdb",
    "snowflake": "snowflake",
    "oracle": "oracle",
    "trino": "trino",
}
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

    def key(self) -> str:
        return f"{','.join(self.columns)}|{self.where}|{self.limit}"

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
    target = _FILTER_DIALECTS.get(dialect)
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
    written: list[str] = []
    for condition in sent:
        copied = condition.copy()
        for c in list(copied.find_all(exp.Column)):
            c.replace(exp.column(exp.to_identifier(spelled[c.name.casefold()], quoted=True)))
        written.append(copied.sql(dialect=target))
    limit = _safe_limit(root, single, len(sent) == len(conditions))
    return Pushed(columns, " AND ".join(f"({w})" for w in written), said, limit)


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
