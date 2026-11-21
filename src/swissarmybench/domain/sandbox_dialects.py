"""A mock client speaks its source's own language over the sandbox (the owner, 2026-11-21: "sometimes the
clients
vary by source ... Things that get built should always hand back to a client that mimics the connections
client
shape").

  [SQL]      a statement in the source's dialect (T-SQL, PostgreSQL, MySQL, Snowflake, SQLite, Oracle, Trino,
             DuckDB) with its driver's parameter marks (?, %s, %(name)s, :name, :1, $1) made DuckDB SQL by
             sqlglot: each mark a numbered parameter in its own order (OFFSET ? ROWS FETCH NEXT ? ROWS keeps
             its
             values), every table named by the sandbox's own name (dbo.orders is orders), SELECT, INSERT,
             UPDATE and DELETE only
  [ODATA]    a Dataverse read's OData $filter ("revenue gt 100000 and contains(name,'Contoso')") and $orderby
  [FETCHXML] a FetchXML query's entity, attributes, filter conditions, orders and top/count
  [LIST]     a SharePoint list read's filters ([["Status", "=", "Open"]])

What cannot be emulated is refused in one sentence that names the feature and its line, never changed quietly.
Pure rules: standard library and sqlglot.
"""

from __future__ import annotations

import functools
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp

from swissarmybench.domain.sandbox import SandboxError, quote

# A connection's dialect (domain/catalogs.py's words) as sqlglot reads it, and its driver's parameter marks.
SQLGLOT: dict[str, str] = {
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
_SENTINEL = "__sabp_{}__"
_SENTINEL_RE = re.compile(r"^__sabp_(\d+)__$")


def dialect_of(dialect: str | None) -> str:
    """A connection's dialect word as this module knows it (duckdb for a file or an empty table)."""
    key = (dialect or "duckdb").strip().lower()
    return {"tsql": "sqlserver", "mssql": "sqlserver", "postgresql": "postgres", "mariadb": "mysql"}.get(
        key, key
    )


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
    kind: str  # select, insert, update, delete
    table: str | None = None  # a write's table
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
    for node_kind in (exp.Column, exp.Var, exp.Identifier):
        for node in list(tree.find_all(node_kind)):
            found = _SENTINEL_RE.match(node.name or "")
            if found:
                node.replace(exp.Parameter(this=exp.Literal.number(int(found.group(1)))))
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


def to_duckdb_many(
    sql: Any, dialect: str | None, sets: Sequence[Any], tables: Iterable[str]
) -> tuple[Translated, list[list[Any]]]:
    """An executemany's statement made DuckDB SQL once, and each parameter set's values in its marks' order
    (the order is read once, from the marks: a set is never scanned again)."""
    if not isinstance(sets, Sequence) or not sets:
        raise SandboxError("executemany takes at least one set of parameters.")
    first = sets[0]
    made = to_duckdb(sql, dialect, first, tables)
    if isinstance(first, Mapping):
        probe: Any = {k: k for k in first}
    else:
        probe = list(range(len(first)))
    word = dialect_of(dialect)
    reads = SQLGLOT[word]
    quoting = "tsql" if reads == "tsql" else "mysql" if reads == "mysql" else "ansi"
    style = PARAMSTYLE[word]
    if style == "qmark" and isinstance(first, Mapping):
        style = "named"
    _, order = marked(str(sql).strip(), probe, style, quoting)
    out: list[list[Any]] = []
    for at, one in enumerate(sets):
        try:
            out.append([one[k] for k in order])
        except (KeyError, IndexError, TypeError):
            raise SandboxError(f"Parameter set {at + 1} does not match the first one's marks.") from None
    return made, out


@functools.lru_cache(maxsize=256)
def plain_insert(sql: str) -> tuple[str, tuple[str, ...] | None, int] | None:
    """A DuckDB INSERT INTO t [(columns)] VALUES ($1, ..., $n), one row of its marks in order: its table, its
    columns (None: every column, in order) and n; else None (any other statement)."""
    try:
        tree = sqlglot.parse_one(sql, read="duckdb")
    except sqlglot.errors.SqlglotError:
        return None
    if not isinstance(tree, exp.Insert) or tree.args.get("returning") or tree.args.get("conflict"):
        return None
    values = tree.expression
    if not isinstance(values, exp.Values) or len(values.expressions) != 1:
        return None
    row = values.expressions[0]
    marks = row.expressions if isinstance(row, exp.Tuple) else []
    numbers = []
    for mark in marks:
        if not isinstance(mark, (exp.Parameter, exp.Placeholder)):
            return None
        try:
            numbers.append(int(str(mark.this.name if isinstance(mark.this, exp.Expression) else mark.this)))
        except (TypeError, ValueError):
            return None
    if not numbers or numbers != list(range(1, len(numbers) + 1)):
        return None
    target = tree.this
    columns: tuple[str, ...] | None = None
    if isinstance(target, exp.Schema):
        columns = tuple(c.name for c in target.expressions)
        target = target.this
    if not isinstance(target, exp.Table) or (columns is not None and len(columns) != len(numbers)):
        return None
    return target.name, columns, len(numbers)


# ===== Dataverse: OData $filter and $orderby, FetchXML =====

_ODATA_TOKEN = re.compile(
    r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<num>-?\d+(?:\.\d+)?)|(?P<word>[A-Za-z_][A-Za-z0-9_./]*)"
    r"|(?P<punct>[(),]))"
)
_ODATA_OPS = {"eq": "=", "ne": "<>", "gt": ">", "ge": ">=", "lt": "<", "le": "<="}
_ODATA_FUNCS = {"contains": "%{}%", "startswith": "{}%", "endswith": "%{}"}


def odata_where(text: Any, columns: Sequence[str]) -> tuple[str, list[Any]]:
    """An OData $filter as a DuckDB WHERE (values bound): eq ne gt ge lt le, and or not, parentheses,
    contains, startswith, endswith, null, true and false. What else it says is refused in one sentence."""
    source = str(text or "").strip()
    if not source:
        return "", []
    tokens: list[tuple[str, str]] = []
    at = 0
    while at < len(source):
        m = _ODATA_TOKEN.match(source, at)
        if not m or m.end() == at:
            if source[at:].strip():
                raise SandboxError(f"The mock's OData $filter cannot read {source[at:].strip()[:30]!r}.")
            break
        kind = m.lastgroup or ""
        tokens.append((kind, m.group(kind)))
        at = m.end()
    by_case = {c.casefold(): c for c in columns}
    params: list[Any] = []
    pos = 0

    def peek() -> tuple[str, str] | None:
        return tokens[pos] if pos < len(tokens) else None

    def take() -> tuple[str, str]:
        nonlocal pos
        if pos >= len(tokens):
            raise SandboxError("The mock's OData $filter ends too soon.")
        pos += 1
        return tokens[pos - 1]

    def value(token: tuple[str, str]) -> str:
        kind, said = token
        if kind == "str":
            params.append(said[1:-1].replace("''", "'"))
            return "?"
        if kind == "num":
            params.append(float(said) if "." in said else int(said))
            return "?"
        low = said.lower()
        if low in ("true", "false"):
            params.append(low == "true")
            return "?"
        if low == "null":
            return "NULL"
        real = by_case.get(said.casefold())
        if real is None:
            raise SandboxError(f"The mock's OData $filter names {said}, which this table has no column for.")
        return quote(real)

    def primary() -> str:
        token = take()
        if token == ("punct", "("):
            inner = disjunction()
            if take() != ("punct", ")"):
                raise SandboxError("The mock's OData $filter has a ( with no ).")
            return f"({inner})"
        if token[0] == "word" and token[1].lower() == "not":
            return f"NOT {primary()}"
        if token[0] == "word" and token[1].lower() in _ODATA_FUNCS and peek() == ("punct", "("):
            take()
            column = value(take())
            if take() != ("punct", ","):
                raise SandboxError(f"The mock's OData {token[1]}() takes a column and a text.")
            text_token = take()
            if text_token[0] != "str":
                raise SandboxError(f"The mock's OData {token[1]}() compares with a quoted text.")
            if take() != ("punct", ")"):
                raise SandboxError(f"The mock's OData {token[1]}() has no ).")
            pattern = _ODATA_FUNCS[token[1].lower()].format(text_token[1][1:-1].replace("''", "'"))
            params.append(pattern)
            return f"{column} ILIKE ?"
        if token[0] == "word" and peek() == ("punct", "("):
            raise SandboxError(f"The mock's OData $filter cannot emulate {token[1]}().")
        left = value(token)
        op_token = take()
        op = _ODATA_OPS.get(op_token[1].lower())
        if op is None:
            raise SandboxError(f"The mock's OData $filter cannot emulate the operator {op_token[1]}.")
        right = value(take())
        if right == "NULL":
            return f"{left} IS {'NOT ' if op == '<>' else ''}NULL"
        return f"{left} {op} {right}"

    def conjunction() -> str:
        parts = [primary()]
        while (t := peek()) is not None and t[0] == "word" and t[1].lower() == "and":
            take()
            parts.append(primary())
        return " AND ".join(parts)

    def disjunction() -> str:
        parts = [conjunction()]
        while (t := peek()) is not None and t[0] == "word" and t[1].lower() == "or":
            take()
            parts.append(conjunction())
        return " OR ".join(parts)

    where = disjunction()
    if pos != len(tokens):
        raise SandboxError(f"The mock's OData $filter cannot read the words after {tokens[pos - 1][1]!r}.")
    return where, params


def order_by(text: Any, columns: Sequence[str]) -> str:
    """An OData $orderby ("name desc, revenue") as DuckDB's ORDER BY's list."""
    by_case = {c.casefold(): c for c in columns}
    parts = []
    for item in str(text or "").split(","):
        bits = item.split()
        if not bits:
            continue
        real = by_case.get(bits[0].casefold())
        if real is None or len(bits) > 2 or (len(bits) == 2 and bits[1].lower() not in ("asc", "desc")):
            raise SandboxError(f"The mock's $orderby cannot read {item.strip()!r}.")
        parts.append(quote(real) + (" DESC" if len(bits) == 2 and bits[1].lower() == "desc" else ""))
    return ", ".join(parts)


_FETCH_OPS = {
    "eq": "=", "ne": "<>", "neq": "<>", "gt": ">", "ge": ">=", "lt": "<", "le": "<=", "like": "LIKE",
    "not-like": "NOT LIKE",
}  # fmt: skip


@dataclass
class Fetch:
    table: str
    sql: str
    params: list[Any]


def fetchxml(text: Any, tables: Iterable[str], columns_of: Any) -> Fetch:
    """A FetchXML query as one DuckDB SELECT: <entity name>, <attribute>s (none or <all-attributes/>: every
    column), <filter type="and|or"> of <condition attribute operator value> (eq ne gt ge lt le like not-like
    null not-null in not-in; nested filters), <order attribute descending>, top or count. Link-entities,
    aggregates and the rest are refused in one sentence. `columns_of(table)` gives a table's columns."""
    try:
        root = ET.fromstring(str(text or ""))  # noqa: S314 (the user's own FetchXML; no DOCTYPE is read)
    except ET.ParseError as error:
        raise SandboxError(f"The FetchXML could not be read: {error}.") from None
    if "<!DOCTYPE" in str(text).upper():
        raise SandboxError("A FetchXML query has no DOCTYPE.")
    if root.tag != "fetch":
        raise SandboxError("A FetchXML query starts with <fetch>.")
    if root.get("aggregate") in ("true", "1"):
        raise SandboxError("The sandbox's mock cannot emulate a FetchXML aggregate.")
    entity = root.find("entity")
    if entity is None or not entity.get("name"):
        raise SandboxError('A FetchXML query names its table: <entity name="account">.')
    known = {t.casefold(): t for t in tables}
    table = known.get(str(entity.get("name")).casefold())
    if table is None:
        raise SandboxError(f"The sandbox has no table {entity.get('name')} here.")
    columns = list(columns_of(table))
    by_case = {c.casefold(): c for c in columns}

    def col(name: Any) -> str:
        real = by_case.get(str(name or "").casefold())
        if real is None:
            raise SandboxError(f"{table} has no column {name}.")
        return quote(real)

    if entity.find("link-entity") is not None:
        raise SandboxError("The sandbox's mock cannot emulate a FetchXML link-entity (a join).")
    picked = [col(a.get("name")) for a in entity.findall("attribute")]
    params: list[Any] = []

    def condition(c: ET.Element) -> str:
        op = str(c.get("operator") or "eq")
        name = col(c.get("attribute"))
        if op == "null":
            return f"{name} IS NULL"
        if op == "not-null":
            return f"{name} IS NOT NULL"
        if op in ("in", "not-in"):
            items = [v.text or "" for v in c.findall("value")]
            if not items:
                raise SandboxError(f"The condition on {c.get('attribute')} ({op}) has no values.")
            params.extend(items)
            return f"{name} {'NOT ' if op == 'not-in' else ''}IN ({', '.join('?' for _ in items)})"
        if op not in _FETCH_OPS:
            raise SandboxError(f"The sandbox's mock cannot emulate the FetchXML operator {op}.")
        params.append(c.get("value"))
        return f"CAST({name} AS VARCHAR) {_FETCH_OPS[op]} ?" if "like" in op else f"{name} {_FETCH_OPS[op]} ?"

    def filtered(f: ET.Element) -> str:
        joiner = " OR " if f.get("type") == "or" else " AND "
        parts = [
            condition(c) if c.tag == "condition" else f"({filtered(c)})"
            for c in f
            if c.tag in ("condition", "filter")
        ]
        return joiner.join(parts) or "TRUE"

    wheres = [filtered(f) for f in entity.findall("filter")]
    orders = [
        col(o.get("attribute")) + (" DESC" if o.get("descending") in ("true", "1") else "")
        for o in entity.findall("order")
    ]
    most = root.get("top") or root.get("count")
    sql = f"SELECT {', '.join(picked) if picked else '*'} FROM {quote(table)}"  # noqa: S608 (checked names)
    if wheres:
        sql += " WHERE " + " AND ".join(f"({w})" for w in wheres)
    if orders:
        sql += " ORDER BY " + ", ".join(orders)
    if most:
        if not str(most).isdigit():
            raise SandboxError("A FetchXML top or count is a whole number.")
        sql += f" LIMIT {int(most)}"
    return Fetch(table, sql, params)


# ===== SharePoint: a list read's filters =====

_LIST_OPS = {"=": "=", "==": "=", "!=": "<>", "<>": "<>", "<": "<", "<=": "<=", ">": ">", ">=": ">="}


def list_where(filters: Any, columns: Sequence[str]) -> tuple[str, list[Any]]:
    """A SharePoint read's filters ([[column, op, value]]: = != <> < <= > >=, in, between, like, is null)."""
    by_case = {c.casefold(): c for c in columns}
    parts: list[str] = []
    params: list[Any] = []
    for item in filters or []:
        if not isinstance(item, (list, tuple)) or len(item) not in (2, 3):
            raise SandboxError("A filter is [column, op, value].")
        column, op = str(item[0]), str(item[1]).lower()
        value = item[2] if len(item) == 3 else None
        real = by_case.get(column.casefold())
        if real is None:
            raise SandboxError(f"The list has no column {column}.")
        name = quote(real)
        if op in _LIST_OPS:
            parts.append(f"{name} {_LIST_OPS[op]} ?")
            params.append(value)
        elif op == "in" and isinstance(value, (list, tuple)) and value:
            parts.append(f"{name} IN ({', '.join('?' for _ in value)})")
            params.extend(value)
        elif op == "between" and isinstance(value, (list, tuple)) and len(value) == 2:
            parts.append(f"{name} BETWEEN ? AND ?")
            params.extend(value)
        elif op == "like":
            parts.append(f"CAST({name} AS VARCHAR) LIKE ?")
            params.append(value)
        elif op in ("is null", "null"):
            parts.append(f"{name} IS NULL")
        elif op in ("is not null", "not null"):
            parts.append(f"{name} IS NOT NULL")
        else:
            raise SandboxError(f"The sandbox's mock cannot emulate the list filter {item[1]!r}.")
    return " AND ".join(parts), params


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
