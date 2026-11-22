"""The sandbox's half of the adapter's query (Plans/adapter.plan.md, 2026-11-22): a statement in its
connection's own language, made DuckDB SQL over the sandbox's tables, so an endpoint's SQL deploys
unchanged against the real source.

  [SQL]      a statement in the source's dialect (T-SQL, PostgreSQL, MySQL, Snowflake, SQLite, Oracle, Trino,
             DuckDB) with its driver's parameter marks (?, %s, %(name)s, :name, :1, $1) made DuckDB SQL by
             sqlglot: each mark a numbered parameter in its own order (OFFSET ? ROWS FETCH NEXT ? ROWS keeps
             its values), every table named by the sandbox's own name (dbo.orders is orders), SELECT, INSERT,
             UPDATE and DELETE only; a view, a query's table or a sequence made or dropped
  [NAMES]    what a query names, checked against a catalog (Will this work for real?), never run

What cannot be emulated is refused in one sentence that names the feature and its line, never changed quietly.
(Dataverse's OData and FetchXML text and a SharePoint list's filters went with the mock clients: an endpoint
reads them with a plan.) Pure rules: standard library and sqlglot.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp

from swissarmybench.domain import catalogs
from swissarmybench.domain.sandbox import SandboxError, check_table_name

# A connection's driver's parameter marks, by its dialect (domain/catalogs.py's words): the dialects the
# mock reads. Each one's name in sqlglot is catalogs.sqlglot_name's (SQLGLOT, below).
# qmark ?, format %s, pyformat %(name)s, named :name, numeric :1, dollar $1
PARAMSTYLE: dict[str, str] = {
    "sqlserver": "qmark",
    "dataverse": "qmark",
    "postgres": "format",
    "mysql": "format",
    "sqlite": "qmark",
    "duckdb": "dollar",
    "snowflake": "format",
    "oracle": "named",
    "trino": "qmark",
}
WORDS: dict[str, str] = {
    "sqlserver": "T-SQL",
    "dataverse": "T-SQL",
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "sqlite": "SQLite",
    "duckdb": "DuckDB SQL",
    "snowflake": "Snowflake SQL",
    "oracle": "Oracle SQL",
    "trino": "Trino SQL",
}
SQLGLOT: dict[str, str] = {word: str(catalogs.sqlglot_name(word)) for word in PARAMSTYLE}
_SENTINEL = "__sabp_{}__"
_SENTINEL_RE = re.compile(r"^__sabp_(\d+)__$")


def dialect_of(dialect: str | None) -> str:
    """A connection's dialect word as this module knows it (duckdb for a file or an empty table)."""
    return catalogs.dialect_word(dialect) or "duckdb"


def line_of(text: str, at: int) -> int:
    return text.count("\n", 0, max(0, at)) + 1


def _word_line(text: str, word: str) -> int:
    found = re.search(r"\b" + re.escape(word) + r"\b", text, re.I)
    return line_of(text, found.start()) if found else 1


# ===== a driver's parameter marks =====


def marked(sql: str, params: Any, style: str, quoting: str = "ansi") -> tuple[str, list[Any]]:
    """Each parameter mark outside strings, quoted names and comments made a numbered sentinel, and the
    values in the sentinels' order. A mark with no value, or a value no mark takes, is said."""
    values: list[Any] = []
    names: dict[str, int] = {}
    by_name = params if isinstance(params, Mapping) else None
    listed = list(params) if isinstance(params, (list, tuple)) else []
    out: list[str] = []
    i, n = 0, len(sql)
    used = 0

    def take_positional(at: int) -> str:
        nonlocal used
        if used >= len(listed):
            raise SandboxError(f"Line {line_of(sql, at)}: a parameter mark has no value (give one per mark).")
        values.append(listed[used])
        used += 1
        return _SENTINEL.format(len(values))

    def take_named(name: str, at: int) -> str:
        if name.isdigit() and by_name is None:
            index = int(name) - 1
            if not 0 <= index < len(listed):
                raise SandboxError(f"Line {line_of(sql, at)}: :{name} has no value.")
            key = f"#{name}"
            if key not in names:
                values.append(listed[index])
                names[key] = len(values)
            return _SENTINEL.format(names[key])
        if by_name is None or name not in by_name:
            raise SandboxError(f"Line {line_of(sql, at)}: the parameter {name} has no value.")
        if name not in names:
            values.append(by_name[name])
            names[name] = len(values)
        return _SENTINEL.format(names[name])

    while i < n:
        c = sql[i]
        if c in "'\"" or (c == "[" and quoting == "tsql") or (c == "`" and quoting == "mysql"):
            close = {"[": "]"}.get(c, c)
            j = i + 1
            while j < n:
                if sql[j] == "\\" and quoting == "mysql" and c != "`":
                    j += 2
                    continue
                if sql[j] == close:
                    if j + 1 < n and sql[j + 1] == close and close != "]":
                        j += 2
                        continue
                    break
                j += 1
            piece = sql[i : j + 1]
            if style in ("format", "pyformat") and c == "'":
                piece = piece.replace("%%", "%")  # the driver's own escape, in a string too
            out.append(piece)
            i = j + 1
            continue
        if sql.startswith("--", i):
            j = sql.find("\n", i)
            j = n if j < 0 else j
            out.append(sql[i:j])
            i = j
            continue
        if sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(sql[i:j])
            i = j
            continue
        if style in ("qmark", "dollar") and c == "?":
            out.append(take_positional(i))
            i += 1
            continue
        if style == "dollar" and c == "$" and i + 1 < n and sql[i + 1].isdigit():
            m = re.match(r"\$(\d+)", sql[i:])
            if m is None:  # pragma: no cover (the character checks above make one)
                raise SandboxError("A parameter mark could not be read.")
            out.append(take_named(m.group(1), i))
            i += len(m.group(0))
            continue
        if style in ("format", "pyformat") and c == "%":
            if sql.startswith("%%", i):
                out.append("%")
                i += 2
                continue
            if sql.startswith("%s", i) and (style == "format" or by_name is None):
                out.append(take_positional(i))
                i += 2
                continue
            m = re.match(r"%\((\w+)\)s", sql[i:])
            if m:
                out.append(take_named(m.group(1), i))
                i += len(m.group(0))
                continue
        if (
            style in ("named", "numeric")
            and c == ":"
            and i + 1 < n
            and (sql[i + 1].isalnum() or sql[i + 1] == "_")
        ):
            if i > 0 and sql[i - 1] == ":":  # a cast (x::int)
                out.append(c)
                i += 1
                continue
            m = re.match(r":(\w+)", sql[i:])
            if m is None:  # pragma: no cover (the character checks above make one)
                raise SandboxError("A parameter mark could not be read.")
            out.append(take_named(m.group(1), i))
            i += len(m.group(0))
            continue
        out.append(c)
        i += 1
    if listed and by_name is None and not names and used != len(listed):
        raise SandboxError(
            f"{len(listed)} values were given for {used} parameter mark{'s' if used != 1 else ''}."
        )
    return "".join(out), values


# ===== a statement in the source's dialect as DuckDB SQL =====


@dataclass
class Translated:
    sql: str
    params: list[Any]
    kind: str  # select, insert, update, delete; a definition: "create view", "drop sequence", ... (DEFINES)
    table: str | None = None  # a write's table (a definition's: what it makes or drops)
    tables: list[str] = field(default_factory=list)


_REFUSED: tuple[tuple[type[exp.Expression], str, str], ...] = (
    (exp.Merge, "MERGE", "MERGE"),
    (exp.Execute, "EXEC", "EXEC"),
    (exp.Create, "CREATE", "a CREATE statement"),
    (exp.Drop, "DROP", "a DROP statement"),
    (exp.Alter, "ALTER", "an ALTER statement"),
    (exp.TruncateTable, "TRUNCATE", "TRUNCATE"),
    (exp.Command, "", "this statement"),
    (exp.Transaction, "BEGIN", "a transaction statement (the mock commits each statement)"),
    (exp.Commit, "COMMIT", "COMMIT in SQL (call the client's commit())"),
    (exp.Rollback, "ROLLBACK", "ROLLBACK in SQL (call the client's rollback())"),
    (exp.Pragma, "PRAGMA", "PRAGMA"),
    (exp.Set, "SET", "SET"),
    (exp.Use, "USE", "USE"),
)
_SYSTEM = {"sys", "information_schema", "pg_catalog", "sqlite_master", "mysql", "performance_schema"}
# What an API may make in the sandbox through its mock (the test app's gap 8; Reset undoes it): a view, a
# table made from a query, a sequence; and drop them again (a table only one an API made: the service checks).
DEFINES = (
    "create view",
    "create table",
    "create sequence",
    "drop view",
    "drop table",
    "drop sequence",
)


def is_definition(kind: str) -> bool:
    return kind in DEFINES


def _definition(tree: exp.Expr, text: str, language: str) -> tuple[exp.Expr, str, exp.Table] | None:
    """A statement that makes or drops a view, a query's table or a sequence: (the tree, its kind as in
    DEFINES, the table node it names); None: any other statement. Anything else CREATE or DROP says is
    refused here, in one sentence."""
    if isinstance(tree, exp.Select) and isinstance(
        tree.args.get("into"), exp.Into
    ):  # T-SQL's SELECT ... INTO
        into = tree.args["into"]
        query = tree.copy()
        query.set("into", None)
        tree = exp.Create(this=into.this.copy(), kind="TABLE", expression=query)
    if not isinstance(tree, (exp.Create, exp.Drop)):
        return None
    verb = "create" if isinstance(tree, exp.Create) else "drop"
    what = str(tree.args.get("kind") or "").lower()
    named = list(tree.args.get("tables") or []) if verb == "drop" else [tree.this]
    line = _word_line(text, verb.upper())
    if verb == "create" and what == "table" and not isinstance(tree.args.get("expression"), exp.Query):
        raise SandboxError(
            f"Line {line}: the sandbox's mock makes a table from a query (CREATE TABLE ... AS SELECT); add a "
            "new empty table on the Sandbox page (Add table…)."
        )
    if what not in ("view", "table", "sequence") or len(named) != 1 or not isinstance(named[0], exp.Table):
        raise SandboxError(
            f"Line {line}: the sandbox's mock makes a view, a table from a query or a sequence, and drops "
            f"them, one at a time ({language})."
        )
    target = named[0]
    try:
        name = check_table_name(target.name)
    except SandboxError as error:
        raise SandboxError(f"Line {line}: {error}") from None
    target.set("this", exp.to_identifier(name, quoted=True))
    target.set("db", None)
    target.set("catalog", None)
    return tree, f"{verb} {what}", target


def _sequence_calls(tree: exp.Expr) -> None:
    """T-SQL's NEXT VALUE FOR s as DuckDB's nextval('s')."""
    for node in list(tree.find_all(exp.NextValueFor)):
        name = node.this.name if isinstance(node.this, (exp.Column, exp.Table)) else str(node.this)
        node.replace(exp.Anonymous(this="nextval", expressions=[exp.Literal.string(check_table_name(name))]))


def to_duckdb(sql: Any, dialect: str | None, params: Any, tables: Iterable[str]) -> Translated:
    """A source's statement made DuckDB SQL over the sandbox's tables (`tables`: the names it may use)."""
    text = str(sql or "").strip()
    if not text:
        raise SandboxError("The statement is empty.")
    word = dialect_of(dialect)
    reads = SQLGLOT.get(word)
    if reads is None:
        raise SandboxError(
            f"The sandbox's mock has no SQL for {dialect}: it reads {', '.join(WORDS.values())}."
        )
    language = WORDS[word]
    quoting = "tsql" if reads == "tsql" else "mysql" if reads == "mysql" else "ansi"
    style = PARAMSTYLE[word]
    if style == "qmark" and isinstance(params, Mapping):
        style = "named"
    marked_sql, values = marked(text, params if params is not None else [], style, quoting)
    out, kind, target, used = _translate(text, marked_sql, reads, language, tuple(tables))
    if kind == "create view" and values:
        raise SandboxError(
            f"Line 1: a view cannot hold a value given apart ({language}): write it in the view's SQL, or "
            "filter the view when it is read."
        )
    return Translated(out, values, kind, target, list(used))


@functools.lru_cache(maxsize=512)
def _translate(
    text: str, marked_sql: str, reads: str, language: str, tables: tuple[str, ...]
) -> tuple[str, str, str | None, tuple[str, ...]]:
    """A statement whose marks are numbered made DuckDB SQL: (its text, kind, a write's table, the tables it
    uses). Kept by its words: an API sends the same few statements again and again with other values, and
    parsing each with sqlglot was most of a small call's time."""
    try:
        statements = [s for s in sqlglot.parse(marked_sql, read=reads) if s is not None]
    except sqlglot.errors.ParseError as error:
        info = error.errors[0] if error.errors else {}
        line = int(info.get("line") or 1)
        said = str(info.get("description") or error).split("\n")[0]
        raise SandboxError(
            f"Line {line}: the sandbox's mock could not read this {language}: {said}."
        ) from None
    except sqlglot.errors.SqlglotError as error:
        raise SandboxError(
            f"The sandbox's mock could not read this {language}: {str(error).splitlines()[0]}."
        ) from None
    if len(statements) != 1:
        raise SandboxError(f"Send one statement at a time ({len(statements)} were sent).")
    tree = statements[0]
    temporary = (
        re.search(r"\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+(#\w+)", text, re.I) if reads == "tsql" else None
    )
    if temporary:
        line = line_of(text, temporary.start(1))
        raise SandboxError(f"Line {line}: the sandbox's mock has no temporary tables ({temporary.group(1)}).")
    if isinstance(tree, exp.Command):
        raise SandboxError(f"Line 1: the sandbox's mock cannot run {str(tree.this).upper()} ({language}).")
    defined = _definition(tree, text, language)
    if defined is not None:
        return _define(*defined, reads, language, tables)
    for refused, keyword, words in _REFUSED:
        if isinstance(tree, refused) or (refused is exp.Merge and tree.find(exp.Merge)):
            line = _word_line(text, keyword or text.split()[0])
            raise SandboxError(f"Line {line}: the sandbox's mock cannot run {words} ({language}).")
    if not isinstance(tree, (exp.Select, exp.SetOperation, exp.Insert, exp.Update, exp.Delete)):
        raise SandboxError(
            f"Line 1: the sandbox's mock runs SELECT, INSERT, UPDATE and DELETE only ({language})."
        )
    known = {t.casefold(): t for t in tables}
    ctes = {c.alias_or_name.casefold() for c in tree.find_all(exp.CTE)}
    used: list[str] = []
    for table in tree.find_all(exp.Table):
        name = table.name
        if not name or (not table.db and name.casefold() in ctes):
            continue
        if name.startswith("#") or name.startswith("@"):
            raise SandboxError(
                f"Line {_word_line(text, name)}: the sandbox's mock has no temporary tables ({name})."
            )
        if (table.db or "").casefold() in _SYSTEM or name.casefold() in _SYSTEM:
            raise SandboxError(
                f"Line {_word_line(text, name)}: the sandbox's mock has no system views ({table.sql(reads)})."
            )
        real = known.get(name.casefold())
        if real is None:
            has = ", ".join(sorted(known.values())[:12]) or "none"
            raise SandboxError(
                f"Line {_word_line(text, name)}: the sandbox has no table {name} here (it has: {has})."
            )
        table.set("this", exp.to_identifier(real, quoted=True))
        table.set("db", None)
        table.set("catalog", None)
        used.append(real)
    _marks(tree)
    _sequence_calls(tree)
    returning = tree.find(exp.Returning)
    if returning is not None:  # T-SQL's OUTPUT INSERTED.id: DuckDB's RETURNING id
        for column in returning.find_all(exp.Column):
            if column.table.casefold() in ("inserted", "deleted"):
                column.set("table", None)
    kind = (
        "insert" if isinstance(tree, exp.Insert)
        else "update" if isinstance(tree, exp.Update)
        else "delete" if isinstance(tree, exp.Delete)
        else "select"
    )  # fmt: skip
    target = None
    if kind != "select":
        written = tree.this if not isinstance(tree.this, exp.Schema) else tree.this.this
        target = written.name if isinstance(written, exp.Table) else (used[0] if used else None)
        target = known.get((target or "").casefold(), target)
    try:
        out = tree.sql("duckdb")
    except sqlglot.errors.UnsupportedError as error:
        raise SandboxError(f"Line 1: the sandbox's mock cannot run this {language}: {error}.") from None
    return out, kind, target, tuple(dict.fromkeys(used))


def _marks(tree: exp.Expr) -> None:
    for node_kind in (exp.Column, exp.Var, exp.Identifier):
        for node in list(tree.find_all(node_kind)):
            found = _SENTINEL_RE.match(node.name or "")
            if found:
                node.replace(exp.Parameter(this=exp.Literal.number(int(found.group(1)))))


def _define(
    tree: exp.Expr, kind: str, target: exp.Table, reads: str, language: str, tables: tuple[str, ...]
) -> tuple[str, str, str | None, tuple[str, ...]]:
    """A definition's DuckDB SQL: the query a view or table is made from uses the sandbox's tables only."""
    known = {t.casefold(): t for t in tables}
    used: list[str] = []
    query = tree.args.get("expression")
    if isinstance(query, exp.Expression):
        ctes = {c.alias_or_name.casefold() for c in query.find_all(exp.CTE)}
        for table in query.find_all(exp.Table):
            name = table.name
            if not name or (not table.db and name.casefold() in ctes):
                continue
            if (table.db or "").casefold() in _SYSTEM or name.casefold() in _SYSTEM:
                raise SandboxError(f"Line 1: the sandbox's mock has no system views ({table.sql(reads)}).")
            real = known.get(name.casefold())
            if real is None:
                has = ", ".join(sorted(known.values())[:12]) or "none"
                raise SandboxError(f"Line 1: the sandbox has no table {name} here (it has: {has}).")
            table.set("this", exp.to_identifier(real, quoted=True))
            table.set("db", None)
            table.set("catalog", None)
            used.append(real)
        _marks(query)
        _sequence_calls(query)
    try:
        out = tree.sql("duckdb")
    except sqlglot.errors.UnsupportedError as error:
        raise SandboxError(f"Line 1: the sandbox's mock cannot run this {language}: {error}.") from None
    return out, kind, target.name, tuple(dict.fromkeys(used))


# ===== "Will this work for real?": what a query names, checked against a catalog (never run) =====


@dataclass
class Named:
    """A table a query names (its schema when it gives one) and the columns it names (unqualified ones are
    the query's single table's when it reads one table, else unknown)."""

    schema: str
    table: str
    columns: list[str] = field(default_factory=list)


def names_in(sql: Any, dialect: str | None) -> list[Named]:
    """The tables and columns a statement names, by sqlglot in the source's dialect (marks made sentinels
    first, so `?` and `%s` parse). A statement it cannot read says so."""
    word = dialect_of(dialect)
    reads = SQLGLOT.get(word, "duckdb")
    quoting = "tsql" if reads == "tsql" else "mysql" if reads == "mysql" else "ansi"
    style = PARAMSTYLE.get(word, "qmark")
    text = str(sql or "")
    count = len(re.findall(r"\?|%s|:\w+|\$\d+", text)) + 5
    try:
        marked_sql, _ = marked(
            text, list(range(count)) if style not in ("named", "pyformat") else {}, style, quoting
        )
    except SandboxError:
        marked_sql = text
    tree = sqlglot.parse_one(marked_sql, read=reads)
    ctes = {c.alias_or_name.casefold() for c in tree.find_all(exp.CTE)}
    tables = [t for t in tree.find_all(exp.Table) if t.name and t.name.casefold() not in ctes]
    by_alias = {(t.alias_or_name or t.name).casefold(): t for t in tables}
    found: dict[tuple[str, str], Named] = {}
    for t in tables:
        found.setdefault((t.db.casefold(), t.name.casefold()), Named(t.db, t.name))
    for column in tree.find_all(exp.Column):
        name = column.name
        if not name or _SENTINEL_RE.match(name) or name == "*":
            continue
        owner = (
            by_alias.get(column.table.casefold())
            if column.table
            else (tables[0] if len(tables) == 1 else None)
        )
        if owner is None:
            continue
        named = found[(owner.db.casefold(), owner.name.casefold())]
        if name not in named.columns:
            named.columns.append(name)
    return list(found.values())
