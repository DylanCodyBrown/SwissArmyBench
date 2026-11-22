"""One record per connection kind (the craft review of 2026-11-22, ranking item 12): the one place a kind
declares itself. Before it, one kind was named in up to 16 domain files, each keeping a table of its own.

A **kind** is a word the app knows a connection by. One record can play up to three parts:

  [TABLES]    a tables kind (the tables contract, domain/connection_tables.py): it has `lists` and `reads`,
              how the service reads it (`reads_with`) and how DuckDB SQL names its tables (`naming`)
  [DIALECT]   a dialect (domain/catalogs.py): the first record of a `dialect` owns it and says its other
              names, its name in sqlglot, which filters go to the source, whether the adapter folds a plan
              into its SQL, how its rows are counted, the mock's marks and words
  [TEMPLATE]  a form's starter (server/blade_templates.py, by its id): its label and group, what it writes
              (or why it is read-only), what only this computer has, its Entra check, its variables' prefix

Every other module's per-kind table is a view of KINDS (the functions below), kept under its old name where
it always was: connection_tables.TABLE_KINDS, PATH_KINDS, VERSIONED; catalogs.DIALECTS and its names in
sqlglot; write_capability.WRITABLE and READ_ONLY; portability.KINDS and FILE_KINDS; app_registrations'
CHECKED_KINDS and AREAS; lakes.KINDS, LABELS and ENV_PREFIX; sandbox_dialects' PARAMSTYLE and WORDS; what
context.md and the pages say of a kind. tests/test_kind_records.py refuses a record with a part half filled
(problems), a table that disagrees with its record, and shows a made-up kind arriving in every view.

This module imports no other module of the app (the kind modules import it, never the other way), so it
breaks no import cycle and the plain client may load it. Standard library only; no I/O.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

# The adapter's write modes (adapter.MODES; tests/test_write_vocabulary.py holds them together).
WRITE_MODES: tuple[str, ...] = ("insert", "update", "merge", "delete", "truncate")
# A file or a sheet is written whole or added to; nothing in it is matched by a key.
WHOLE_MODES: tuple[str, ...] = ("insert", "truncate")

NEVER: str = "-"  # a dialect whose text sqlglot never reads (DAX, SharePoint)
OTHER: str = "other"  # the dialect of a kind that names none
BY_TEMPLATE: str = "template"  # `writes_as`: a database's engine or a file's format decides its writes

READS_WITH: tuple[str, ...] = ("sql", "dax", "code", "file", "own")
NAMINGS: tuple[str, ...] = ("database", "powerbi", "path", "single", "file")
FILTERS: tuple[str, ...] = ("sql", "structured", "none")
COUNTS: tuple[str, ...] = ("query", "partitions")

DATABASES: str = "Databases"
FILES: str = "Files"
OWN_CODE: str = "Your own code"
LAKES: str = "Lakes and SharePoint"


@dataclass(frozen=True)
class Writable:
    operations: tuple[str, ...]  # its Write starters' words
    how: str  # in plain words: native SQL in one transaction, the Web API's change sets...
    note: str = ""  # a limit worth saying beside the starters
    modes: tuple[str, ...] = WRITE_MODES  # the adapter's modes sab.write takes on it


@dataclass(frozen=True)
class Kind:
    name: str
    label: str  # what people call it (a starter's own label)
    group: str = ""  # its group on the Connections page and the form; "" when it has no card there
    # ----- [TABLES] the tables contract -----
    lists: str = ""  # how it lists its tables, in words; "" when it is not a tables kind
    reads: str = ""  # how it reads one, in words
    reads_with: str = ""  # sql (a SELECT in its own SQL), dax, code (its own read), file, own (the sandbox)
    naming: str = ""  # how DuckDB SQL names its tables: database, powerbi, path, single, file
    versions: bool = False  # a table takes a version or a time after @
    query_tab: bool = False  # a query tab runs on it (Query from, the New query page)
    names_schema: bool = True  # sab.read names its schema (Dataverse's Web API has one: no)
    own_page: bool = False  # it has a page of its own (an API: the APIs page), not a Connections card
    datasets: bool = False  # its tables are grouped by dataset (a Power BI workspace)
    grouped_by: str = ""  # what its tree calls a group of tables ("": a folder for paths, else a schema)
    actions: tuple[str, ...] = ()  # what its card's detail offers beside the usual
    # ----- [DIALECT] said once, by the first record of the dialect -----
    dialect: str = ""  # its word in catalogs.DIALECTS; "" for a kind that names none ("other")
    aliases: tuple[str, ...] = ()  # the dialect's other names
    sqlglot: str = ""  # the dialect's name in sqlglot, or NEVER
    filters: str = ""  # a query's conditions sent to the source: sql (its own SQL), structured, none
    adapter: bool = False  # the adapter reads it itself, the plan folded into its SQL (adapter.DIALECTS)
    count: str = ""  # how its rows are counted before a read: query (COUNT(*)), partitions (SQL Server)
    paramstyle: str = ""  # its driver's marks, for the sandbox's mock ("" : the mock does not read it)
    sql_words: str = ""  # its SQL in words (T-SQL), for the mock's refusals
    by_code: bool = False  # read through its own code (sab.read), not a SQL session of its own
    sql_cell: bool = True  # a %%sql cell runs on it
    secrets: str = ""  # the form's heading over its secrets ("" : Passwords)
    test_tells: bool = False  # a Test says what the server is: the card is drawn again with it
    # ----- [TEMPLATE] -----
    own_sql: bool = False  # its starter keeps its own older SELECT though the adapter reads its dialect
    writes: Writable | None = None
    read_only: str = ""  # why it is read-only, in words
    writes_as: str = ""  # BY_TEMPLATE, or the kind whose writes are its own (dataverse_web: dataverse)
    local_only: str = ""  # the note it carries whatever its sign-in (portability's rule, by its key)
    reads_files: bool = False  # its code reads a file or folder: on this disk unless a web or cloud address
    entra_area: str = ""  # its area in an app registration's access report; "" : not checked
    entra_scope: str = ""  # the token's scope ({url}: the connection's own address)
    entra_place: tuple[tuple[str, ...], str] = ((), "")  # the settings its check names, and their joiner
    entra_refusals: str = ""  # whose words a refusal is said in: sql, dataverse, graph, storage
    env_prefix: str = ""  # the prefix of the variable names its form suggests

    @property
    def paths(self) -> bool:
        """Its tables are named by their folders."""
        return self.naming == "path"

    @property
    def tables(self) -> bool:
        return bool(self.lists)


_SQL = ("append", "create", "replace", "upsert", "delete")
_DELTA = ("append", "overwrite", "merge", "delete", "optimize", "vacuum")
_LOADERS = (
    "a warehouse takes rows through its own bulk loads (its stage or storage), not from a notebook's rows"
)
_GRAPH = "https://graph.microsoft.com/.default"
_STORAGE = "https://storage.azure.com/.default"


def _reads_only(label: str, what: str = "") -> str:
    return f"the app reads {what or label}; it has no write starters for it"


_RECORDS: tuple[Kind, ...] = (
    # ===== SQL databases: each a dialect of its own, a form's starter by the same word =====
    Kind(
        "sqlserver",
        "SQL Server",
        DATABASES,
        dialect="sqlserver",
        aliases=("tsql", "mssql", "sql server", "azuresql"),
        sqlglot="tsql",
        filters="sql",
        adapter=True,
        count="partitions",
        paramstyle="qmark",
        sql_words="T-SQL",
        test_tells=True,
        actions=("import_relationships",),  # its foreign keys into the ERD
        writes=Writable(_SQL, "T-SQL in one transaction: staged, MERGE, retried on passing errors"),
        entra_area="Azure SQL",
        entra_scope="https://database.windows.net/.default",
        entra_place=(("database", "server"), " on "),
        entra_refusals="sql",
    ),
    Kind(
        "azuresql",
        "Azure SQL Database / Synapse",
        DATABASES,
        dialect="sqlserver",
        writes=Writable(_SQL, "T-SQL in one transaction: staged, MERGE, retried on Azure's passing errors"),
    ),
    Kind(
        "sybase",
        "SAP ASE (Sybase)",
        DATABASES,
        dialect="sqlserver",
        own_sql=True,  # T-SQL without OFFSET ... FETCH
        count="query",  # COUNT(*): SAP ASE has no sys.partitions, which SQL Server's count reads
        read_only=_reads_only("SAP ASE"),
        local_only="sybase",
    ),
    Kind(
        "postgres",
        "PostgreSQL",
        DATABASES,
        dialect="postgres",
        aliases=("postgresql", "pg", "redshift"),
        sqlglot="postgres",
        filters="sql",
        adapter=True,
        count="query",
        paramstyle="format",
        sql_words="PostgreSQL",
        writes=Writable(_SQL, "SQL in one transaction (COPY, ON CONFLICT)"),
    ),
    Kind("redshift", "Amazon Redshift", DATABASES, dialect="postgres", read_only=_LOADERS),
    Kind(
        "mysql",
        "MySQL",
        DATABASES,
        dialect="mysql",
        aliases=("mariadb",),
        sqlglot="mysql",
        filters="sql",
        adapter=True,
        count="query",
        paramstyle="format",
        sql_words="MySQL",
        writes=Writable(_SQL, "SQL in one transaction (ON DUPLICATE KEY UPDATE)"),
    ),
    Kind(
        "mariadb",
        "MariaDB",
        DATABASES,
        dialect="mysql",
        writes=Writable(_SQL, "SQL in one transaction (ON DUPLICATE KEY UPDATE)"),
    ),
    Kind(
        "sqlite",
        "SQLite",
        DATABASES,
        dialect="sqlite",
        sqlglot="sqlite",
        filters="sql",
        adapter=True,
        count="query",
        paramstyle="qmark",
        sql_words="SQLite",
        writes=Writable(_SQL, "SQL in one transaction (the file opened again to write)"),
        reads_files=True,
    ),
    Kind(
        "duckdb",
        "DuckDB file",
        DATABASES,
        dialect="duckdb",
        sqlglot="duckdb",
        filters="sql",
        adapter=True,
        count="query",
        paramstyle="dollar",
        sql_words="DuckDB SQL",
        read_only="the connection opens the file read-only: DuckDB lets one program write a file at a time",
        reads_files=True,
    ),
    Kind(
        "snowflake",
        "Snowflake",
        DATABASES,
        dialect="snowflake",
        sqlglot="snowflake",
        filters="sql",
        adapter=True,
        count="query",
        paramstyle="format",
        sql_words="Snowflake SQL",
        read_only=_LOADERS,
    ),
    Kind(
        "databricks",
        "Databricks",
        DATABASES,
        dialect="databricks",
        sqlglot="databricks",
        filters="sql",
        adapter=True,
        count="query",
        paramstyle="named",
        sql_words="Databricks SQL",
        read_only=_LOADERS,
    ),
    Kind(
        "oracle",
        "Oracle",
        DATABASES,
        dialect="oracle",
        sqlglot="oracle",
        filters="sql",
        adapter=True,
        count="query",
        paramstyle="named",
        sql_words="Oracle SQL",
        writes=Writable(_SQL, "SQL in one transaction (MERGE)"),
    ),
    Kind(
        "trino",
        "Trino / Presto",
        DATABASES,
        dialect="trino",
        aliases=("presto",),
        sqlglot="trino",
        filters="sql",
        adapter=True,
        count="query",
        paramstyle="qmark",
        sql_words="Trino SQL",
        writes=Writable(
            ("append", "create", "replace", "upsert", "delete"),
            "SQL, row batches without a transaction (replace one statement where the catalog has it: "
            "Iceberg)",
            "depends on the catalog's connector: Iceberg, Delta Lake and Hive write; a connector that cannot "
            "is refused in Trino's own words",
        ),
    ),
    # ===== databases the app reads in their own SQL, with no dialect of their own here =====
    Kind("bigquery", "Google BigQuery", DATABASES, read_only=_LOADERS),
    Kind("db2", "IBM Db2", DATABASES, read_only=_reads_only("Db2")),
    Kind("teradata", "Teradata", DATABASES, read_only=_reads_only("Teradata")),
    Kind("clickhouse", "ClickHouse", DATABASES, read_only=_reads_only("ClickHouse")),
    Kind("saphana", "SAP HANA", DATABASES, read_only=_reads_only("SAP HANA")),
    Kind("vertica", "Vertica", DATABASES, read_only=_reads_only("Vertica")),
    Kind(
        "access",
        "Microsoft Access",
        DATABASES,
        read_only=_reads_only("Access files"),
        local_only="access",
    ),
    Kind(
        "odbc",
        "Any ODBC data source",
        DATABASES,
        writes=Writable(("append", "create", "replace", "delete"), "SQL, where the source's driver writes"),
        local_only="odbc",
    ),
    # ===== the tables kinds (the contract's two calls), in the contract's order =====
    Kind(
        "database",
        "A database",
        DATABASES,
        lists="its catalog (the connection's own query of its information schema)",
        reads="a SELECT in its own SQL (select_sql)",
        reads_with="sql",
        naming="database",
        query_tab=True,
        writes_as=BY_TEMPLATE,
    ),
    Kind(
        "powerbi",
        "Power BI workspace",
        DATABASES,
        lists="its datasets (the catalog's schemas), then each dataset's tables",
        reads="DAX on the table's dataset: EVALUATE 'Table'",
        reads_with="dax",
        naming="powerbi",
        query_tab=True,
        datasets=True,
        grouped_by="dataset",
        dialect="dax",  # each dataset (semantic model) a schema; its language is DAX
        aliases=("powerbi", "power bi"),
        sqlglot=NEVER,
        filters="none",
        count="query",
        secrets="App registration",
        read_only="a semantic model takes no rows: write its source, then refresh it (Power BI refresh "
        "dataset)",
    ),
    Kind(
        "dataverse",
        "Dataverse",
        DATABASES,
        lists="its read-only SQL endpoint's own catalog (TDS, port 5558: INFORMATION_SCHEMA)",
        reads="a T-SQL SELECT on the SQL endpoint",
        reads_with="sql",
        naming="single",
        query_tab=True,
        dialect="dataverse",  # its SQL endpoint's T-SQL, every table in one schema (dbo)
        sqlglot="tsql",
        filters="sql",
        count="query",
        paramstyle="qmark",
        sql_words="T-SQL",
        by_code=True,
        secrets="App registration",
        writes=Writable(
            ("create", "update", "upsert", "delete", "truncate"),
            "the Web API's $batch change sets (its SQL endpoint is read-only)",
        ),
        entra_area="Dataverse",
        entra_scope="{url}/.default",  # the environment's own
        entra_place=(("url",), ""),
        entra_refusals="dataverse",
    ),
    Kind(
        "dataverse_web",
        "Dataverse (Web API)",
        DATABASES,
        lists="its Web API's metadata (a connection saved before the SQL endpoint was the default)",
        reads="the Web API's read (switch it to the SQL endpoint on its card)",
        reads_with="code",
        naming="single",
        names_schema=False,  # Dataverse's one schema needs no naming
        actions=("sql_endpoint",),  # one click moves it to its SQL endpoint
        dialect="dataverse",
        writes_as="dataverse",  # its Web API writes either way
    ),
    Kind(
        "python",
        "Python (your own code)",
        OWN_CODE,
        lists="its List the tables box",
        reads="its Read a table box",
        reads_with="code",
        naming="single",
        read_only="a connection made of your own Python reads tables: write in a cell of your own code",
    ),
    Kind(
        "api",
        "An API",
        OWN_CODE,
        lists="its web calls that return a table (the API's List the tables)",
        reads="the web call (Read a table)",
        reads_with="code",
        naming="single",
        own_page=True,
        read_only="an API writes through the APIs page's Write rows with this call",
    ),
    Kind(
        "file",
        "A file",
        FILES,
        lists="the file itself: one table, or a workbook's sheets",
        reads="DuckDB's reader, or the sheet",
        reads_with="file",
        naming="file",
        writes_as=BY_TEMPLATE,
    ),
    Kind(
        "csv",
        "A CSV file",
        FILES,
        writes=Writable(("create", "replace"), "a new file, then put in its place", modes=WHOLE_MODES),
        reads_files=True,
    ),
    Kind(
        "excel",
        "An Excel workbook",
        FILES,
        writes=Writable(
            ("create", "replace", "append"),
            "a sheet written, the workbook's other sheets kept",
            modes=WHOLE_MODES,
        ),
        reads_files=True,
    ),
    Kind(
        "parquet",
        "A Parquet file",
        FILES,
        writes=Writable(("create", "replace"), "a new file, then put in its place", modes=WHOLE_MODES),
        reads_files=True,
    ),
    Kind(
        "json",
        "A JSON file",
        FILES,
        writes=Writable(("create", "replace"), "a new file, then put in its place", modes=WHOLE_MODES),
        reads_files=True,
    ),
    Kind(
        "folder",
        "A folder of files",
        FILES,
        lists="its files",
        reads="the file (a workbook's first sheet)",
        reads_with="file",
        naming="file",
        writes=Writable(
            ("create", "replace", "append"),
            "files in the folder, partitioned Parquet among them",
            modes=WHOLE_MODES,
        ),
        reads_files=True,
    ),
    # Lakes and SharePoint (domain/lakes.py): the connection's own code lists, reads and writes them
    # (domain/lake_code.py LakeWrites, domain/sharepoint.py SharePointLists). Each kind's template id is its
    # dialect too; a lake's %%sql is DuckDB's (every table a view), a Fabric SQL endpoint's T-SQL.
    Kind(
        "onelake",
        "Microsoft Fabric OneLake",
        LAKES,
        lists="a lakehouse's Delta tables (Tables/) and files (Files/), by the OneLake DFS endpoint's "
        "listing; a warehouse's INFORMATION_SCHEMA on its SQL endpoint",
        reads="DuckDB's delta_scan, read_parquet or read_csv (else the deltalake package, else its Delta "
        "log read here); T-SQL on a warehouse's SQL endpoint",
        reads_with="code",
        naming="path",
        versions=True,
        query_tab=True,
        dialect="onelake",
        sqlglot="duckdb",
        filters="structured",
        count="query",
        by_code=True,
        writes=Writable(
            (*_DELTA, "create"),
            "a lakehouse's Delta tables (the deltalake package) and its Files/ (Parquet, CSV)",
            "a warehouse is written with T-SQL in its own tools",
        ),
        entra_area="OneLake",
        entra_scope=_STORAGE,
        entra_place=(("workspace", "item"), "/"),
        entra_refusals="storage",
        env_prefix="ONELAKE",
    ),
    Kind(
        "datalake",
        "Azure Data Lake Storage",
        LAKES,
        lists="its container's Parquet, CSV and JSON files, Delta folders and partitioned folders (the ADLS "
        "Gen2 listing)",
        reads="DuckDB's read_parquet, read_csv or delta_scan, over HTTPS with the sign-in's token",
        reads_with="code",
        naming="path",
        versions=True,
        query_tab=True,
        dialect="datalake",
        sqlglot="duckdb",
        filters="structured",
        count="query",
        by_code=True,
        writes=Writable(
            (*_DELTA, "create"),
            "its Delta tables (the deltalake package), and Parquet or CSV files through the ADLS Gen2 API",
        ),
        entra_area="Data Lake",
        entra_scope=_STORAGE,
        entra_place=(("account", "container", "folder_in_container"), "/"),
        entra_refusals="storage",
        env_prefix="DATALAKE",
    ),
    Kind(
        "delta",
        "Delta Lake",
        LAKES,
        lists="every folder holding a _delta_log under its root, to a depth",
        reads="DuckDB's delta_scan (else the deltalake package, else its Delta log read here); a version "
        "or a time after @",
        reads_with="code",
        naming="path",
        versions=True,
        query_tab=True,
        dialect="delta",
        sqlglot="duckdb",
        filters="structured",
        count="query",
        by_code=True,
        writes=Writable(
            _DELTA,
            "a Delta commit a write (the deltalake package): merge by keys, delete by a condition",
            "vacuum keeps 7 days unless the cell says otherwise",
        ),
        entra_area="Data Lake",
        entra_scope=_STORAGE,
        entra_place=(("root",), ""),
        entra_refusals="storage",
        env_prefix="DELTA_LAKE",
    ),
    Kind(
        "sharepoint",
        "SharePoint lists",
        LAKES,
        lists="the site's lists (Microsoft Graph)",
        reads="Graph's list items, paged, $select and $filter sent",
        reads_with="code",
        naming="single",
        grouped_by="list",
        query_tab=True,
        dialect="sharepoint",
        sqlglot=NEVER,
        filters="structured",
        count="query",
        by_code=True,
        sql_cell=False,  # read by code only
        writes=Writable(
            ("create", "update", "delete", "truncate"),
            "Microsoft Graph's $batch, retried on 429 (a list has no transaction)",
        ),
        entra_area="SharePoint",
        entra_scope=_GRAPH,
        entra_place=(("site_url",), ""),
        entra_refusals="graph",
        env_prefix="SHAREPOINT",
    ),
    # The open project's sandbox (domain/sandbox.py): local test data, never live; never exported as a
    # connection (an export names the real connection a table is Mocked as, or none). It writes only by
    # itself (a local sandbox API's mock clients, its grid's edits).
    Kind(
        "sandbox",
        "Sandbox",
        lists="the project's sandbox's tables (its own DuckDB file, sandbox/)",
        reads="the table whole, from the sandbox (following every write)",
        reads_with="own",
        naming="single",
        read_only="the sandbox is written by its local sandbox API and its grid's edits, not a Write starter",
    ),
    Kind(
        "sharepoint_docs",
        "SharePoint documents",
        LAKES,
        lists="each document library's file index, and its tabular documents (CSV, Parquet, JSON lines, a "
        "workbook's sheets and named tables)",
        reads="Graph's file index; a document downloaded into memory, kept by its eTag",
        reads_with="code",
        naming="path",
        query_tab=True,
        dialect="sharepoint_docs",
        sqlglot=NEVER,
        filters="structured",
        count="query",
        by_code=True,
        sql_cell=False,
        read_only="its tables are its documents: upload a file with the SharePoint upload file starter",
        entra_area="SharePoint",
        entra_scope=_GRAPH,
        entra_place=(("site_url",), ""),
        entra_refusals="graph",
        env_prefix="SHAREPOINT",
    ),
)

KINDS: dict[str, Kind] = {kind.name: kind for kind in _RECORDS}

# The fields only the first record of a dialect says (a later record of the same dialect inherits them).
_DIALECT_FIELDS: tuple[str, ...] = (
    "aliases",
    "sqlglot",
    "filters",
    "adapter",
    "count",
    "paramstyle",
    "sql_words",
    "by_code",
    "sql_cell",
    "secrets",
    "test_tells",
)


def _all(records: Mapping[str, Kind] | None) -> Mapping[str, Kind]:
    return KINDS if records is None else records


def group_word(name: str | None, records: Mapping[str, Kind] | None = None) -> str:
    """What a tables kind's tree calls a group of its tables: dataset, list, folder or schema."""
    kind = get(name, records)
    if kind is None:
        return "schema"
    return kind.grouped_by or ("folder" if kind.paths else "schema")


def get(name: str | None, records: Mapping[str, Kind] | None = None) -> Kind | None:
    """A kind's record by its word (a tables kind, a template's id); None for a word nobody declared."""
    return _all(records).get(str(name or ""))


def engines(records: Mapping[str, Kind] | None = None) -> dict[str, Kind]:
    """Each dialect's own record (the first that names it), by the dialect's word, in order."""
    out: dict[str, Kind] = {}
    for kind in _all(records).values():
        if kind.dialect:
            out.setdefault(kind.dialect, kind)
    return out


def aliases(records: Mapping[str, Kind] | None = None) -> dict[str, str]:
    """Another name for a dialect -> the dialect's word (tsql: sqlserver)."""
    return {alias: word for word, kind in engines(records).items() for alias in kind.aliases}


_ENGINES: dict[str, Kind] = engines()
_ALIASES: dict[str, str] = aliases()


def engine(dialect: str | None, records: Mapping[str, Kind] | None = None) -> Kind | None:
    """A dialect's own record, by any of its names in any case; None for "other" and unknown words."""
    key = str(dialect or "").strip().lower()
    if records is None:
        return _ENGINES.get(_ALIASES.get(key, key))
    return engines(records).get(aliases(records).get(key, key))


def problems(records: Mapping[str, Kind] | None = None) -> list[str]:
    """What is wrong with the records, one sentence each (none: every part a record plays is whole)."""
    kinds = _all(records)
    owners = engines(kinds)
    out: list[str] = []
    taken: dict[str, str] = {}
    for name, kind in kinds.items():

        def say(words: str, name: str = name) -> None:
            out.append(f"{name}: {words}")

        if name != kind.name:
            say(f"filed under another word than its name {kind.name!r}")
        if not kind.label:
            say("has no label")
        if bool(kind.lists) != bool(kind.reads):
            say("says how it lists its tables or how it reads one, not both")
        if kind.tables:
            if kind.reads_with not in READS_WITH:
                say(f"reads_with is one of {', '.join(READS_WITH)}")
            if kind.naming not in NAMINGS:
                say(f"naming is one of {', '.join(NAMINGS)}")
        elif kind.reads_with or kind.naming or kind.versions or kind.query_tab or kind.datasets:
            say("has a tables kind's fields but does not say how it lists and reads")
        if kind.versions and not kind.paths:
            say("has versions, so its tables are paths")
        decided = [bool(kind.writes), bool(kind.read_only), bool(kind.writes_as)]
        if decided.count(True) != 1:
            say("says exactly one of: what it writes, why it is read-only, whose writes are its own")
        if kind.writes_as and kind.writes_as != BY_TEMPLATE:
            other = kinds.get(kind.writes_as)
            if other is None or not (other.writes or other.read_only):
                say(f"writes as {kind.writes_as!r}, which does not say what it writes")
        if kind.writes is not None:
            if not kind.writes.operations or not kind.writes.how:
                say("writes, but not which operations or how")
            if not set(kind.writes.modes) <= set(WRITE_MODES):
                say("has a write mode the adapter does not have")
        if bool(kind.entra_area) != bool(kind.entra_scope and kind.entra_place[0] and kind.entra_refusals):
            say("an Entra check names its area, scope, place and whose refusals, all four")
        if kind.dialect and owners[kind.dialect] is kind:
            if kind.sqlglot == "":
                say("a dialect says its name in sqlglot, or NEVER")
            if kind.filters not in FILTERS:
                say(f"filters is one of {', '.join(FILTERS)}")
            if kind.filters == "sql" and kind.sqlglot == NEVER:
                say("filters in its own SQL need its name in sqlglot")
            if kind.count not in COUNTS:
                say(f"count is one of {', '.join(COUNTS)}")
            if bool(kind.paramstyle) != bool(kind.sql_words):
                say("the mock reads it with both its marks and its words, or neither")
            for alias in (kind.dialect, *kind.aliases):
                if taken.setdefault(alias, kind.dialect) != kind.dialect:
                    say(f"the name {alias!r} is {taken[alias]}'s already")
        else:
            # A starter may count its own way (SAP ASE speaks T-SQL but has no sys.partitions); the rest is
            # its dialect's own record's.
            blank = Kind("", "")
            said = [f for f in _DIALECT_FIELDS if f != "count" and getattr(kind, f) != getattr(blank, f)]
            if said:
                whose = owners[kind.dialect].name if kind.dialect else "no dialect"
                say(f"{', '.join(said)} are said once, by its dialect's own record ({whose})")
    return out


# ===== the views: every other module's per-kind table, derived =====


def tables_contract(records: Mapping[str, Kind] | None = None) -> dict[str, tuple[str, str]]:
    """connection_tables.TABLE_KINDS: how each tables kind lists its tables and reads one."""
    return {k.name: (k.lists, k.reads) for k in _all(records).values() if k.tables}


def path_kinds(records: Mapping[str, Kind] | None = None) -> frozenset[str]:
    """connection_tables.PATH_KINDS: the kinds whose tables are named by their folders."""
    return frozenset(k.name for k in _all(records).values() if k.paths)


def versioned(records: Mapping[str, Kind] | None = None) -> frozenset[str]:
    """connection_tables.VERSIONED: the kinds whose tables take a version or a time after @."""
    return frozenset(k.name for k in _all(records).values() if k.versions)


def dialects(records: Mapping[str, Kind] | None = None) -> tuple[str, ...]:
    """catalogs.DIALECTS: every dialect's word, "other" last."""
    return (*engines(records), OTHER)


def sqlglot_names(records: Mapping[str, Kind] | None = None) -> dict[str, str]:
    """catalogs' one table of a dialect's name in sqlglot."""
    return {word: k.sqlglot for word, k in engines(records).items() if k.sqlglot not in ("", NEVER)}


def no_sqlglot(records: Mapping[str, Kind] | None = None) -> tuple[str, ...]:
    """catalogs.NO_SQLGLOT: the dialects whose text sqlglot never reads."""
    return (*(word for word, k in engines(records).items() if k.sqlglot == NEVER), OTHER)


def structured_filters(records: Mapping[str, Kind] | None = None) -> tuple[str, ...]:
    """The dialects that take a query's conditions as (column, op, value), applied by their own code."""
    return tuple(word for word, k in engines(records).items() if k.filters == "structured")


def adapter_dialects(records: Mapping[str, Kind] | None = None) -> tuple[str, ...]:
    """The dialects the adapter reads itself, the plan folded into their SQL."""
    return tuple(word for word, k in engines(records).items() if k.adapter)


def own_sql(records: Mapping[str, Kind] | None = None) -> tuple[str, ...]:
    """The starters that keep their own SELECT though the adapter reads their dialect."""
    return tuple(k.name for k in _all(records).values() if k.own_sql)


def paramstyles(records: Mapping[str, Kind] | None = None) -> dict[str, str]:
    """sandbox_dialects.PARAMSTYLE: the dialects the mock reads, each with its driver's marks."""
    return {word: k.paramstyle for word, k in engines(records).items() if k.paramstyle}


def sql_words(records: Mapping[str, Kind] | None = None) -> dict[str, str]:
    """sandbox_dialects.WORDS: each of those dialects' SQL in words."""
    return {word: k.sql_words for word, k in engines(records).items() if k.sql_words}


def writable(records: Mapping[str, Kind] | None = None) -> dict[str, Writable]:
    """write_capability.WRITABLE."""
    return {k.name: k.writes for k in _all(records).values() if k.writes is not None}


def read_only(records: Mapping[str, Kind] | None = None) -> dict[str, str]:
    """write_capability.READ_ONLY: each read-only kind with why."""
    return {k.name: k.read_only for k in _all(records).values() if k.read_only}


def writes_by_template(records: Mapping[str, Kind] | None = None) -> frozenset[str]:
    """The tables kinds whose writes are their template's (a database's engine, a file's format)."""
    return frozenset(k.name for k in _all(records).values() if k.writes_as == BY_TEMPLATE)


def writes_same(records: Mapping[str, Kind] | None = None) -> dict[str, str]:
    """A kind whose writes are another's (dataverse_web: dataverse)."""
    return {k.name: k.writes_as for k in _all(records).values() if k.writes_as not in ("", BY_TEMPLATE)}


def local_only(records: Mapping[str, Kind] | None = None) -> dict[str, str]:
    """portability.KINDS, by each note's key: a kind that leans on this computer whatever its sign-in."""
    return {k.name: k.local_only for k in _all(records).values() if k.local_only}


def file_kinds(records: Mapping[str, Kind] | None = None) -> frozenset[str]:
    """portability.FILE_KINDS: the kinds whose code reads a file or folder."""
    return frozenset(k.name for k in _all(records).values() if k.reads_files)


def entra_scopes(records: Mapping[str, Kind] | None = None) -> dict[str, str]:
    """app_registrations.CHECKED_KINDS: each checked kind's scope ("" : the connection's own address)."""
    return {
        k.name: "" if "{" in k.entra_scope else k.entra_scope for k in _all(records).values() if k.entra_area
    }


def entra_areas(records: Mapping[str, Kind] | None = None) -> dict[str, str]:
    """app_registrations.AREAS: each checked kind's area in the report, in words."""
    return {k.name: k.entra_area for k in _all(records).values() if k.entra_area}


def in_group(group: str, records: Mapping[str, Kind] | None = None) -> tuple[str, ...]:
    """The dialects of a group, in order (lakes.KINDS: Lakes and SharePoint)."""
    return tuple(word for word, k in engines(records).items() if k.group == group)


def labels(names: Iterable[str], records: Mapping[str, Kind] | None = None) -> dict[str, str]:
    kinds = _all(records)
    return {name: kinds[name].label for name in names}


def env_prefixes(records: Mapping[str, Kind] | None = None) -> dict[str, str]:
    """lakes.ENV_PREFIX: the prefix of the variable names a kind's form suggests."""
    return {k.name: k.env_prefix for k in _all(records).values() if k.env_prefix}
