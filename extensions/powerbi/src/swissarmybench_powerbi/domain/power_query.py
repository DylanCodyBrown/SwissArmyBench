"""Power Query (M) for a table, from where it came from: the one place each source kind's M is written, table
driven (KINDS), and read back (the import's reverse, `read_source`). The owner, 2026-11-19: "Make a powerbi
desktop file with our model exported" / "import the model, preserving connections".

  [SOURCE]  MSource: a table's source kind (sqlserver, postgres, mysql, snowflake, databricks, oracle,
            dataverse, sharepoint, csv, excel, parquet, datalake, onelake, delta), its settings as their
            boxes' text (`${NAME}` kept: design principle 12.7), its place (database, schema, table), a file's
            path and sheet, and a native query in the source's own SQL
  [WRITE]   m_for(source): the partition's M: the connector's function, its navigation to the table (or the
            native query: Sql.Database's Query option, else Value.NativeQuery), a CSV's or a sheet's header
            promoted and its columns typed. Every `${NAME}` is a Power Query parameter of that name
            (#"NAME"); never a password, token or secret: Power BI Desktop asks for credentials itself
  [STEPS]   native_steps(): a grid's steps (their one DuckDB query, domain/codegen.py) transpiled by sqlglot
            to the source's dialect around its table; None with the reason when sqlglot cannot carry a
            function or DuckDB's own SQL faithfully. Steps are never translated into M here
  [READ]    read_source(m): the source and its navigation read back from a partition's M (the import): the
            connector's call, its literal or parameter arguments, the schema/item step or a Query option;
            anything after the navigation is "its Power Query steps", not translated

Pure rules: standard library and sqlglot, no I/O.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, SqlglotError

from swissarmybench.domain import variable_refs as refs

# A connection's template (server/blade_templates.py) or tables kind (domain/connection_tables.py) -> the M
# kind.
TEMPLATE_KINDS: dict[str, str] = {
    "sqlserver": "sqlserver",
    "azuresql": "sqlserver",
    "postgres": "postgres",
    "mysql": "mysql",
    "mariadb": "mysql",
    "snowflake": "snowflake",
    "databricks": "databricks",
    "oracle": "oracle",
    "dataverse": "dataverse",
    "sharepoint": "sharepoint",
    "csv": "csv",
    "excel": "excel",
    "parquet": "parquet",
    "datalake": "datalake",
    "onelake": "onelake",
    "delta": "delta",
}
# A file opened by itself: its extension -> the M kind.
FILE_KINDS: dict[str, str] = {
    ".csv": "csv",
    ".tsv": "csv",
    ".txt": "csv",
    ".xlsx": "excel",
    ".xlsm": "excel",
    ".xls": "excel",
    ".parquet": "parquet",
}
# Each database kind's SQL as sqlglot names it (the steps are transpiled to it).
DIALECTS: dict[str, str] = {
    "sqlserver": "tsql",
    "postgres": "postgres",
    "mysql": "mysql",
    "snowflake": "snowflake",
    "databricks": "databricks",
    "oracle": "oracle",
    "dataverse": "tsql",
}
# Power BI's data types (TMDL dataType) -> M's type names, for a file's columns typed.
M_TYPES: dict[str, str] = {
    "int64": "Int64.Type",
    "double": "type number",
    "decimal": "Currency.Type",
    "string": "type text",
    "dateTime": "type datetime",
    "boolean": "type logical",
}


class PowerQueryError(ValueError):
    """A table's source that has no M here; the message says why."""


@dataclass(frozen=True)
class MSource:
    kind: str
    settings: Mapping[str, str] = field(default_factory=dict)  # setting name -> its box's text
    database: str = ""
    schema: str = ""
    table: str = ""
    path: str = ""  # a file's path (its box's text) or a lake table's path in its store
    sheet: str = ""
    query: str = ""  # a native query, in the source's own SQL
    delimiter: str = ","


@dataclass(frozen=True)
class MText:
    """A partition's M, and the Power Query parameters it names (each `${NAME}`), in order."""

    text: str
    parameters: tuple[str, ...] = ()


# ===== values as M =====


def m_string(value: str) -> str:
    """A text as an M string literal (a double quote doubled; a line break as #(lf))."""
    escaped = value.replace('"', '""').replace("\r", "#(cr)").replace("\n", "#(lf)").replace("\t", "#(tab)")
    return f'"{escaped}"'


def m_name(name: str) -> str:
    """An identifier as M writes any name: #"name" (so a keyword or a space is safe)."""
    return '#"' + name.replace('"', '""') + '"'


class _Params:
    def __init__(self) -> None:
        self.names: list[str] = []

    def text(self, value: str) -> str:
        """A box's text as an M expression: a literal, a parameter, or both joined with &."""
        pieces: list[str] = []
        for part in refs.parts(value):
            if isinstance(part, refs.Ref):
                if part.name not in self.names:
                    self.names.append(part.name)
                pieces.append(m_name(part.name))
            else:
                pieces.append(m_string(part))
        return " & ".join(pieces) if pieces else '""'


def _setting(source: MSource, *names: str) -> str:
    for name in names:
        value = source.settings.get(name)
        if value not in (None, ""):
            return str(value)
    return ""


def _need(value: str, what: str, kind: str) -> str:
    if not value:
        raise PowerQueryError(f"its {KINDS[kind].label} connection names no {what}")
    return value


def _let(steps: Sequence[tuple[str, str]]) -> str:
    """let ... in <last step>, one step a line (four spaces in, as Power BI Desktop writes it)."""
    body = ",\n".join(f"    {name} = {value}" for name, value in steps)
    return f"let\n{body}\nin\n    {steps[-1][0]}"


def _server(source: MSource, p: _Params, kind: str) -> str:
    server = _need(_setting(source, "server", "data source", "address"), "server", kind)
    port = _setting(source, "port")
    joined = server + (":" + port if port and not refs.holds(port) else "")
    return p.text(joined)


def _navigate(source: MSource) -> list[tuple[str, str]]:
    item = m_string(source.table)
    if source.schema:
        return [("Navigation", f"Source{{[Schema={m_string(source.schema)},Item={item}]}}[Data]")]
    return [("Navigation", f"Source{{[Item={item}]}}[Data]")]


def _native(source: MSource) -> list[tuple[str, str]]:
    return [
        ("Navigation", f"Value.NativeQuery(Source, {m_string(source.query)}, null, [EnableFolding=true])")
    ]


def _sqlserver(source: MSource, p: _Params) -> list[tuple[str, str]]:
    server = p.text(_need(_setting(source, "server", "data source"), "server", "sqlserver"))
    database = p.text(_need(_setting(source, "database") or source.database, "database", "sqlserver"))
    if source.query:
        return [("Source", f"Sql.Database({server}, {database}, [Query={m_string(source.query)}])")]
    return [("Source", f"Sql.Database({server}, {database})"), *_navigate(source)]


def _postgres(source: MSource, p: _Params) -> list[tuple[str, str]]:
    database = p.text(_need(_setting(source, "database") or source.database, "database", "postgres"))
    head = [("Source", f"PostgreSQL.Database({_server(source, p, 'postgres')}, {database})")]
    return head + (_native(source) if source.query else _navigate(source))


def _mysql(source: MSource, p: _Params) -> list[tuple[str, str]]:
    database = p.text(_need(_setting(source, "database") or source.database, "database", "mysql"))
    server = _server(source, p, "mysql")
    if source.query:
        return [("Source", f"MySQL.Database({server}, {database}, [Query={m_string(source.query)}])")]
    nav = replace_schema(source, source.schema or _setting(source, "database") or source.database)
    return [("Source", f"MySQL.Database({server}, {database})"), *_navigate(nav)]


def replace_schema(source: MSource, schema: str) -> MSource:
    return MSource(source.kind, source.settings, source.database, schema, source.table, query=source.query)


def _snowflake(source: MSource, p: _Params) -> list[tuple[str, str]]:
    account = _need(_setting(source, "account", "server"), "account", "snowflake")
    host = account if "." in account or refs.holds(account) else account + ".snowflakecomputing.com"
    warehouse = p.text(_setting(source, "warehouse"))
    database = _setting(source, "database") or source.database
    head = [("Source", f"Snowflake.Databases({p.text(host)}, {warehouse})")]
    db = f'Source{{[Name={p.text(_need(database, "database", "snowflake"))},Kind="Database"]}}[Data]'
    if source.query:
        return [
            *head,
            ("Database", db),
            (
                "Navigation",
                f"Value.NativeQuery(Database, {m_string(source.query)}, null, [EnableFolding=true])",
            ),
        ]
    schema = m_string(source.schema or "PUBLIC")
    return [
        *head,
        ("Database", db),
        ("Schema", f'Database{{[Name={schema},Kind="Schema"]}}[Data]'),
        ("Navigation", f'Schema{{[Name={m_string(source.table)},Kind="Table"]}}[Data]'),
    ]


def _databricks(source: MSource, p: _Params) -> list[tuple[str, str]]:
    host = p.text(_need(_setting(source, "server"), "server host name", "databricks"))
    path = p.text(_need(_setting(source, "http path"), "HTTP path", "databricks"))
    catalog = source.database or _setting(source, "catalog") or "hive_metastore"
    head = [
        ("Source", f"Databricks.Catalogs({host}, {path}, null)"),
        ("Catalog", f'Source{{[Name={m_string(catalog)},Kind="Database"]}}[Data]'),
    ]
    if source.query:
        return [
            *head,
            (
                "Navigation",
                f"Value.NativeQuery(Catalog, {m_string(source.query)}, null, [EnableFolding=true])",
            ),
        ]
    return [
        *head,
        ("Schema", f'Catalog{{[Name={m_string(source.schema or "default")},Kind="Schema"]}}[Data]'),
        ("Navigation", f'Schema{{[Name={m_string(source.table)},Kind="Table"]}}[Data]'),
    ]


def _oracle(source: MSource, p: _Params) -> list[tuple[str, str]]:
    server = p.text(_need(_setting(source, "data source", "server", "service"), "server", "oracle"))
    if source.query:
        return [("Source", f"Oracle.Database({server}, [Query={m_string(source.query)}])")]
    return [("Source", f"Oracle.Database({server})"), *_navigate(source)]


def _host(url: str) -> str:
    """https://contoso.crm.dynamics.com/ -> contoso.crm.dynamics.com (a variable's text is kept as it is)."""
    if refs.holds(url):
        return url
    return re.sub(r"^[a-z]+://", "", url.strip(), flags=re.IGNORECASE).split("/", 1)[0]


def _dataverse(source: MSource, p: _Params) -> list[tuple[str, str]]:
    host = _host(_need(_setting(source, "address", "url"), "environment address", "dataverse"))
    head = [("Source", f"CommonDataService.Database({p.text(host)})")]
    return head + (
        _native(source) if source.query else _navigate(replace_schema(source, source.schema or "dbo"))
    )


def _sharepoint(source: MSource, p: _Params) -> list[tuple[str, str]]:
    site = p.text(_need(_setting(source, "site_url", "address", "url"), "site address", "sharepoint"))
    return [
        ("Source", f"SharePoint.Tables({site}, [ApiVersion = 15])"),
        ("Navigation", f"Source{{[Title={m_string(source.table)}]}}[Items]"),
    ]


def _file(source: MSource, p: _Params) -> str:
    return f"File.Contents({p.text(_need(source.path, 'file', source.kind))})"


def _csv(source: MSource, p: _Params) -> list[tuple[str, str]]:
    delimiter = m_string(source.delimiter or ",")
    return [
        (
            "Source",
            f"Csv.Document({_file(source, p)}, [Delimiter={delimiter}, Encoding=65001, "
            "QuoteStyle=QuoteStyle.Csv])",
        ),
        ("Promoted", "Table.PromoteHeaders(Source, [PromoteAllScalars=true])"),
    ]


def _excel(source: MSource, p: _Params) -> list[tuple[str, str]]:
    sheet = m_string(source.sheet or "Sheet1")
    return [
        ("Source", f"Excel.Workbook({_file(source, p)}, null, true)"),
        ("Sheet", f'Source{{[Item={sheet},Kind="Sheet"]}}[Data]'),
        ("Promoted", "Table.PromoteHeaders(Sheet, [PromoteAllScalars=true])"),
    ]


def _parquet(source: MSource, p: _Params) -> list[tuple[str, str]]:
    return [("Source", f"Parquet.Document({_file(source, p)})")]


def _lake_url(source: MSource) -> str:
    """The table's address in its store, as a box's text (`${NAME}` kept)."""
    path = source.path.strip("/")
    if source.kind == "onelake":
        workspace = _need(_setting(source, "workspace"), "workspace", "onelake")
        item = _need(_setting(source, "item"), "item", "onelake")
        return f"https://onelake.dfs.fabric.microsoft.com/{workspace}/{item}/{path}"
    if source.kind == "delta":
        root = _need(_setting(source, "root"), "root", "delta")
        match = re.match(r"abfss://([^@]+)@([^/]+)/?(.*)$", root)
        if (
            match
        ):  # abfss://container@account.dfs.core.windows.net/lake -> https://account.dfs.../container/lake
            container, host, rest = match.groups()
            root = f"https://{host}/{container}" + (f"/{rest.strip('/')}" if rest.strip("/") else "")
        if not root.lower().startswith("https://") and not refs.holds(root):
            raise PowerQueryError(
                "its Delta tables are in a folder on this computer or in S3, which Power Query does "
                "not read as Delta"
            )
        return f"{root.rstrip('/')}/{path}"
    account = _need(_setting(source, "account"), "storage account", "datalake")
    container = _need(_setting(source, "container"), "container", "datalake")
    folder = _setting(source, "folder_in_container").strip("/")
    parts = [f"https://{account}.dfs.core.windows.net", container, folder, path]
    return "/".join(x for x in parts if x)


def _lake(source: MSource, p: _Params) -> list[tuple[str, str]]:
    url = _lake_url(source)
    if source.kind == "delta" or (source.kind == "onelake" and source.path.strip("/").startswith("Tables/")):
        return [
            ("Source", f"AzureStorage.DataLake({p.text(url)}, [HierarchicalNavigation=false])"),
            ("Navigation", "DeltaLake.Table(Source)"),
        ]
    if not url.lower().endswith(".parquet"):
        raise PowerQueryError("only its Parquet files and Delta tables are read by Power Query here")
    return [
        ("Source", f"AzureStorage.DataLake({p.text(url)}, [HierarchicalNavigation=false])"),
        ("Navigation", "Parquet.Document(Source{0}[Content])"),
    ]


@dataclass(frozen=True)
class MKind:
    label: str
    build: Callable[[MSource, _Params], list[tuple[str, str]]]
    typed: bool = False  # its columns come as text (a CSV, a sheet): typed after the header


KINDS: dict[str, MKind] = {
    "sqlserver": MKind("SQL Server", _sqlserver),
    "postgres": MKind("PostgreSQL", _postgres),
    "mysql": MKind("MySQL", _mysql),
    "snowflake": MKind("Snowflake", _snowflake),
    "databricks": MKind("Databricks", _databricks),
    "oracle": MKind("Oracle", _oracle),
    "dataverse": MKind("Dataverse", _dataverse),
    "sharepoint": MKind("SharePoint", _sharepoint),
    "csv": MKind("CSV", _csv, typed=True),
    "excel": MKind("Excel", _excel, typed=True),
    "parquet": MKind("Parquet", _parquet),
    "datalake": MKind("Data Lake", _lake),
    "onelake": MKind("OneLake", _lake),
    "delta": MKind("Delta Lake", _lake),
}


def m_for(source: MSource, types: Sequence[tuple[str, str]] = ()) -> MText:
    """The partition's M for `source`; `types` (column, Power BI data type) type a CSV's or a sheet's columns.
    Raises PowerQueryError (the reason, in words) for a kind with no M here."""
    kind = KINDS.get(source.kind)
    if kind is None:
        raise PowerQueryError(f"Power Query has no reader here for a {source.kind} source")
    p = _Params()
    steps = kind.build(source, p)
    if kind.typed and types:
        pairs = ", ".join(f"{{{m_string(c)}, {M_TYPES.get(t, 'type text')}}}" for c, t in types)
        steps = [*steps, ("Typed", f"Table.TransformColumnTypes({steps[-1][0]}, {{{pairs}}})")]
    return MText(_let(steps), tuple(p.names))


def parquet_rows(file_name: str, parameter: str) -> MText:
    """A table whose rows were written as Parquet beside the model: read from the DataFolder parameter."""
    text = _let([("Source", f"Parquet.Document(File.Contents({m_name(parameter)} & {m_string(file_name)}))")])
    return MText(text, (parameter,))


def parameter_line(name: str, value: str) -> str:
    """A Power Query parameter's expression (expressions.tmdl): a text value, required."""
    return f'{m_string(value)} meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'


# ===== a grid's steps, sent as the source's own SQL =====


@dataclass(frozen=True)
class Native:
    sql: str | None  # the steps as the source's SQL; None: not carried
    why: str = ""  # why not, in words


def native_steps(
    view_query: str,
    variable: str,
    kind: str,
    schema: str,
    table: str,
    base_query: str = "",
    database: str = "",
) -> Native:
    """The grid's steps (their one DuckDB query, reading `variable`) as the source's own SQL around its table
    (or around `base_query`, the source's own query the table was read with)."""
    dialect = DIALECTS.get(kind)
    if dialect is None:
        return Native(None, f"a {KINDS[kind].label if kind in KINDS else kind} source takes no SQL")
    try:
        tree = sqlglot.parse_one(view_query, read="duckdb")
        unknown = sorted({f.name for f in tree.find_all(exp.Anonymous)})
        if unknown:
            return Native(None, f"{', '.join(unknown)} has no faithful {dialect} form")
        duckdb_only = _duckdb_only(tree, dialect)
        if duckdb_only:
            return Native(None, f"{duckdb_only} has no faithful {dialect} form")
        targets = [t for t in tree.find_all(exp.Table) if t.name == variable and not t.args.get("db")]
        if not targets:
            return Native(None, "its query does not read the table")
        if base_query:
            inner = sqlglot.parse_one(base_query, read=dialect)
            replacement: exp.Expression = exp.Subquery(
                this=inner, alias=exp.TableAlias(this=exp.to_identifier(variable))
            )
        else:
            replacement = exp.Table(
                this=exp.to_identifier(table, quoted=True),
                db=exp.to_identifier(schema, quoted=True) if schema else None,
                catalog=exp.to_identifier(database, quoted=True)
                if database and kind == "databricks"
                else None,
                alias=exp.TableAlias(this=exp.to_identifier(variable)),
            )
        for target in targets:
            target.replace(replacement.copy())
        return Native(tree.sql(dialect=dialect, unsupported_level=ErrorLevel.RAISE, pretty=True))
    except SqlglotError as error:
        return Native(None, f"sqlglot cannot carry it to {dialect} ({str(error).splitlines()[0][:160]})")


def _duckdb_only(tree: Any, dialect: str) -> str:
    """DuckDB's own SQL that sqlglot passes through unchanged to a dialect without it (said, never sent)."""
    for star in tree.find_all(exp.Star):
        if any(star.args.get(k) for k in ("except", "except_", "replace", "rename", "ilike")):
            return "SELECT * EXCLUDE/REPLACE"
    for group in tree.find_all(exp.Group):
        if group.args.get("all"):
            return "GROUP BY ALL"
    if dialect in ("tsql", "postgres", "mysql", "oracle") and any(True for _ in tree.find_all(exp.Qualify)):
        return "QUALIFY"
    if any(True for _ in tree.find_all(exp.Columns)):
        return "COLUMNS(...)"
    return ""


# ===== reading a partition's M back (the import) =====

_CALL = re.compile(
    r"(?P<fn>Sql\.Databases?|PostgreSQL\.Database|MySQL\.Database|Snowflake\.Databases|Databricks\.Catalogs"
    r"|Oracle\.Database|CommonDataService\.Database|SharePoint\.Tables|AzureStorage\.DataLake|Csv\.Document"
    r"|Excel\.Workbook|Parquet\.Document)\s*\("
)
_FUNCTION_KINDS: dict[str, str] = {
    "Sql.Database": "sqlserver",
    "Sql.Databases": "sqlserver",
    "PostgreSQL.Database": "postgres",
    "MySQL.Database": "mysql",
    "Snowflake.Databases": "snowflake",
    "Databricks.Catalogs": "databricks",
    "Oracle.Database": "oracle",
    "CommonDataService.Database": "dataverse",
    "SharePoint.Tables": "sharepoint",
    "AzureStorage.DataLake": "datalake",
    "Csv.Document": "csv",
    "Excel.Workbook": "excel",
    "Parquet.Document": "parquet",
}


@dataclass(frozen=True)
class ReadSource:
    """A partition's source read back: its MSource (settings: `${NAME}` for a parameter), whether steps
    follow its navigation, and the reason when it could not be read."""

    source: MSource | None
    steps_after: bool = False
    why: str = ""


def _arguments(text: str, start: int) -> tuple[list[str], int]:
    """The call's top-level arguments (as written) from the character after its "(", and where it ends."""
    depth, at, quoted = 0, start, False
    args: list[str] = []
    current = start
    while at < len(text):
        ch = text[at]
        if quoted:
            if ch == '"':
                if text[at + 1 : at + 2] == '"':
                    at += 1
                else:
                    quoted = False
        elif ch == '"':
            quoted = True
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                args.append(text[current:at].strip())
                return [a for a in args if a], at
            depth -= 1
        elif ch == "," and depth == 0:
            args.append(text[current:at].strip())
            current = at + 1
        at += 1
    raise PowerQueryError("its M is not complete")


def _value(arg: str, parameters: Mapping[str, str]) -> str | None:
    """An argument as a box's text: a literal, or a parameter as `${NAME}`; parts joined by &. None: an
    expression of another kind."""
    out: list[str] = []
    for piece in _split_amp(arg):
        piece = piece.strip()
        literal = re.fullmatch(r'"((?:[^"]|"")*)"', piece)
        if literal:
            out.append(refs.escape(_unescape(literal.group(1))))
            continue
        name = re.fullmatch(r'#"((?:[^"]|"")*)"|([A-Za-z_][A-Za-z0-9_.]*)', piece)
        if name:
            found = (name.group(1) or "").replace('""', '"') or name.group(2) or ""
            if found in parameters and refs.is_name(found):
                out.append("${" + found + "}")
                continue
        return None
    return "".join(out)


def _unescape(text: str) -> str:
    return text.replace('""', '"').replace("#(lf)", "\n").replace("#(cr)", "\r").replace("#(tab)", "\t")


def _split_amp(arg: str) -> list[str]:
    pieces, current, quoted = [], "", False
    for ch in arg:
        if ch == '"':
            quoted = not quoted
        if ch == "&" and not quoted:
            pieces.append(current)
            current = ""
        else:
            current += ch
    pieces.append(current)
    return pieces


def _record(text: str) -> dict[str, str]:
    """[Schema="dbo",Item="orders"] or [Query="..."] -> its fields' literal values."""
    return {
        m.group(1): _unescape(m.group(2))
        for m in re.finditer(r'(?:#")?([A-Za-z]+)"?\s*=\s*"((?:[^"]|"")*)"', text)
    }


def read_source(m: str, parameters: Mapping[str, str] = {}) -> ReadSource:
    """The source a partition's M reads, from its connector call and the navigation after it."""
    found = _CALL.search(m)
    if found is None:
        head = re.search(r"=\s*([A-Za-z][A-Za-z0-9]*\.[A-Za-z]+)\s*\(", m)
        said = head.group(1) if head else "no connector we know"
        return ReadSource(None, why=f"its source is {said}, which this app has no connection for")
    fn = found.group("fn")
    kind = _FUNCTION_KINDS[fn]
    try:
        args, end = _arguments(m, found.end())
    except PowerQueryError as error:
        return ReadSource(None, why=str(error))
    values = [_value(a, parameters) for a in args]
    rest = m[end + 1 :]
    options = _record(args[-1]) if args and args[-1].startswith("[") else {}
    nav = _record(rest[:400])
    settings: dict[str, str] = {}
    database = schema = table = query = path = sheet = ""
    query = options.get("Query", "")
    native = re.search(r'Value\.NativeQuery\([^,]+,\s*"((?:[^"]|"")*)"', rest)
    if native:
        query = _unescape(native.group(1))

    def first(index: int, what: str) -> str:
        value = values[index] if index < len(values) else None
        if value is None:
            raise PowerQueryError(f"its {what} is an expression, not a value")
        return value

    try:
        if kind in ("sqlserver", "postgres", "mysql"):
            settings["server"] = first(0, "server")
            if len(args) > 1 and not args[1].startswith("["):
                settings["database"] = database = first(1, "database")
        elif kind == "oracle":
            settings["server"] = first(0, "server")
        elif kind == "snowflake":
            settings["account"] = first(0, "account")
            settings["warehouse"] = first(1, "warehouse") if len(args) > 1 else ""
        elif kind == "databricks":
            settings["server"] = first(0, "server host name")
            settings["http path"] = first(1, "HTTP path")
        elif kind == "dataverse":
            settings["address"] = "https://" + first(0, "environment")
        elif kind == "sharepoint":
            settings["site_url"] = first(0, "site")
            table = nav.get("Title", "")
        elif kind == "datalake":
            kind, settings, path = _lake_back(first(0, "address"), "DeltaLake.Table(" in rest)
        else:  # a file: Csv.Document(File.Contents("..."))
            inner = re.match(r"File\.Contents\((.*)\)\s*$", args[0] if args else "", re.DOTALL)
            if inner is None:
                return ReadSource(None, why="its file is not read from a path (File.Contents)")
            value = _value(inner.group(1), parameters)
            if value is None:
                return ReadSource(None, why="its file's path is an expression, not a value")
            path = value
            sheet = nav.get("Item", "") if kind == "excel" else ""
    except PowerQueryError as error:
        return ReadSource(None, why=str(error))
    if kind in ("sqlserver", "postgres", "mysql", "oracle", "dataverse") and not query:
        schema, table = nav.get("Schema", ""), nav.get("Item", "")
    if kind in ("snowflake", "databricks") and not query:
        names = re.findall(r'\{\[Name\s*=\s*"((?:[^"]|"")*)"', rest)
        if len(names) >= 3:
            database, schema, table = (_unescape(n) for n in names[:3])
    if not (table or query or path):
        return ReadSource(None, why="its navigation to a table was not found")
    source = MSource(kind, settings, database, schema, table, path=path, sheet=sheet, query=query)
    return ReadSource(source, steps_after=_steps_after(m, kind))


def _lake_back(url: str, delta: bool) -> tuple[str, dict[str, str], str]:
    """A lake address read back into its connection's settings and the table's path."""
    one = re.match(r"https://onelake\.dfs\.fabric\.microsoft\.com/([^/]+)/([^/]+)/(.+)$", url)
    if one:
        return "onelake", {"workspace": one.group(1), "item": one.group(2)}, one.group(3)
    adls = re.match(r"https://([^./]+)\.dfs\.core\.windows\.net/([^/]+)/?(.*)$", url)
    if delta:
        root, _, table = url.rstrip("/").rpartition("/")
        if adls:
            inner = root.split("/", 4)[4] if root.count("/") >= 4 else ""
            root = f"abfss://{adls.group(2)}@{adls.group(1)}.dfs.core.windows.net" + (
                f"/{inner}" if inner else ""
            )
        return "delta", {"root": root}, table
    if adls:
        return "datalake", {"account": adls.group(1), "container": adls.group(2)}, adls.group(3)
    return "datalake", {"address": url}, url


_NAVIGATION_STEPS = re.compile(
    r"^(Source|Navigation|Database|Schema|Catalog|Sheet|Promoted|Typed|Promoted Headers|Changed Type|dbo_\w+|"
    r"[A-Za-z0-9_]+_Table|[A-Za-z0-9_]+_Sheet)$",
    re.IGNORECASE,
)


def _steps_after(m: str, kind: str) -> bool:
    """Whether the M does more than read its source and navigate to the table (its own Power Query steps)."""
    steps = re.findall(r'^\s*(#"[^"]+"|[A-Za-z_][A-Za-z0-9_]*)\s*=', m, re.MULTILINE)
    names = [s[2:-1] if s.startswith('#"') else s for s in steps]
    return any(not _NAVIGATION_STEPS.match(n) for n in names[1:])


def as_json(source: MSource) -> dict[str, Any]:
    return {
        "kind": source.kind,
        "label": KINDS[source.kind].label if source.kind in KINDS else source.kind,
        "settings": dict(source.settings),
        **{k: v for k, v in (("database", source.database), ("schema", source.schema), ("table",
        source.table),
                             ("path", source.path), ("sheet", source.sheet), ("query", source.query)) if v},
    }  # fmt: skip
