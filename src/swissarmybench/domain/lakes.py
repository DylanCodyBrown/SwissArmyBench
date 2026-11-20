# ruff: noqa: E501 (the connections' code is text, written as it runs; its lines are its own)
"""Lakes and SharePoint as connections (the owner, 2026-11-17: "OneLake, Data Lake and SharePoint as
connections, each exposing tables DuckDB can query, by the rule we just set" / "Delta lake as well").

Five kinds, each a starter with its own form, card and code (server/blade_templates.py), each listing
its tables and reading one through the one contract (domain/connection_tables.py):

  onelake          Microsoft Fabric OneLake: a lakehouse's Delta tables (Tables/) and its files (Files/:
                   CSV, Parquet), through the OneLake DFS endpoint; a warehouse's tables by T-SQL on its
                   SQL endpoint (TDS, port 1433, the Entra token beside the connection string)
  datalake         Azure Data Lake Storage Gen2 / Blob storage: a container and folder; its Parquet, CSV
                   and JSON files, Delta folders and hive-partitioned folders, one table each
  delta            Delta Lake: every folder holding a _delta_log under a root (a folder here, abfss://,
                   s3://), found to a depth; time travel (orders@v12, orders@2026-11-01)
  sharepoint       SharePoint lists (Microsoft Graph): a site's lists, typed by their column definitions
  sharepoint_docs  SharePoint documents: each library's file index, and its tabular documents (CSV,
                   Parquet, JSON lines; a workbook's sheets and named tables) as tables

They are database connections (kind sql, each its own dialect) whose catalog and read are the
connection's own code (`catalog = conn.catalog()`, READ below), as Dataverse's Web API was. The three
lake kinds share one Delta and file reader (domain/lake_code.py), the two SharePoint kinds one Graph
client (domain/sharepoint.py), all five one sign-in (domain/entra.py).

Names in DuckDB SQL (domain/connection_tables.py): a table's folders, then its name, after the
connection: `[Lake].sales.orders`, `[Fabric].orders`, `[Fabric].Files.raw."sales.csv"` (or
`[Fabric].Files.raw.sales`), `[Team Docs].Documents.Finance."Budget 2026.xlsx".Summary`. The last
parts are enough when they name one table (`[Team Docs]."Budget 2026.xlsx".Summary`). A Delta table at a
version or a time: `[Lake].sales."orders@v12"`, `[Lake].sales."orders@2026-11-01"` (quoted, so any SQL
reads it; unquoted `orders@v12` after a connection's name is quoted for you).

Pure rules and text: no I/O.
"""

from __future__ import annotations

import re

from swissarmybench.domain import entra
from swissarmybench.domain import lake_code as code
from swissarmybench.domain.sql_server import TOKEN_CODE

ONELAKE: str = "onelake"
DATALAKE: str = "datalake"
DELTA: str = "delta"
SHAREPOINT: str = "sharepoint"
SHAREPOINT_DOCS: str = "sharepoint_docs"
# Each kind's template id is its dialect too.
KINDS: tuple[str, ...] = (ONELAKE, DATALAKE, DELTA, SHAREPOINT, SHAREPOINT_DOCS)
LAKE_KINDS: frozenset[str] = frozenset({ONELAKE, DATALAKE, DELTA})
GROUP: str = "Lakes and SharePoint"  # the Connections page's group for them
LABELS: dict[str, str] = {
    ONELAKE: "Microsoft Fabric OneLake",
    DATALAKE: "Azure Data Lake Storage",
    DELTA: "Delta Lake",
    SHAREPOINT: "SharePoint lists",
    SHAREPOINT_DOCS: "SharePoint documents",
}

# The connection's own read, run after its code (domain/connection_tables.py's read for these kinds):
# its rows (Arrow) and how many there are, the columns and filters the query sends.
READ: str = "conn.rows(table, schema=schema, limit=limit, columns=columns, filters=filters, frame=frame)"
CATALOG: str = "catalog = conn.catalog()"
# The kinds whose read takes filters as DuckDB applies them (the lake kinds), or as OData (SharePoint).
FILTER_DIALECTS: dict[str, str] = {ONELAKE: "lake", DATALAKE: "lake", DELTA: "lake", SHAREPOINT: "odata",
                                   SHAREPOINT_DOCS: "odata"}  # fmt: skip
# A Delta table's version or time, after its name: orders@v12, orders@2026-11-01, orders@2026-11-01T09:30.
AT = re.compile(r"@(?:[vV]\d+|\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?)?)$")


def is_kind(dialect: str | None) -> bool:
    return dialect in KINDS


def read_with(how: str) -> str:
    """How a read was made, in words: "delta_scan" -> DuckDB's delta_scan; "graph ($filter sent)" ->
    Microsoft Graph ($filter sent)."""
    word, _, rest = how.partition(" ")
    return (code.READ_WITH.get(word, word) + (f" {rest}" if rest else "")).strip()


def cell_words(dialect: str) -> str:
    """What a %%sql cell on one of these runs, in words."""
    if dialect in (SHAREPOINT, SHAREPOINT_DOCS):
        return f"{LABELS[dialect]}: no SQL of its own; its tables in DuckDB SQL by name ([Connection].table)"
    if dialect == ONELAKE:
        return (
            "a Fabric lakehouse or warehouse: T-SQL on its SQL endpoint, else DuckDB SQL (every table a view)"
        )
    return f"{LABELS.get(dialect, dialect)}: DuckDB SQL here, every table a view (sales.orders)"


def path_parts(database: str, schema: str, table: str) -> list[str]:
    """A table's place as the parts its SQL name is made of: its folders, then its name (a workbook's
    sheet after its file)."""
    return [p for p in (database, *schema.split("/"), *table.split("/")) if p]


def split_at(name: str) -> tuple[str, str]:
    """A table's name and its @version or @time (empty when none): orders@v12 -> (orders, @v12)."""
    found = AT.search(name)
    return (name[: found.start()], found.group(0)) if found else (name, "")


# ===== each setting from an environment variable (the owner, 2026-11-17: "All should be mapable to env
# vars") =====

# The names the form suggests, per kind and setting (editable).
ENV_PREFIX: dict[str, str] = {
    ONELAKE: "ONELAKE",
    DATALAKE: "DATALAKE",
    DELTA: "DELTA_LAKE",
    SHAREPOINT: "SHAREPOINT",
    SHAREPOINT_DOCS: "SHAREPOINT",
}
_ENV_WORDS: dict[str, str] = {
    "tenant_id": "TENANT_ID",
    "client_id": "CLIENT_ID",
    "username": "USERNAME",
    "site": "SITE_URL",
    "workspace": "WORKSPACE",
    "item": "ITEM",
    "sql endpoint": "SQL_ENDPOINT",
    "account": "ACCOUNT",
    "container": "CONTAINER",
    "folder in container": "FOLDER",
    "root": "ROOT",
    "region": "REGION",
    "profile": "PROFILE",
    "managed identity client id": "MANAGED_CLIENT_ID",
    "access key id": "ACCESS_KEY_ID",
    "library": "LIBRARY",
}


def suggested_env(kind: str | None, setting: str) -> str | None:
    """The variable a setting of these kinds is offered as: SharePoint, tenant -> SHAREPOINT_TENANT_ID."""
    prefix = ENV_PREFIX.get(str(kind or ""))
    word = _ENV_WORDS.get(setting)
    if prefix is None or word is None:
        return None
    if kind == DELTA and setting == "access key id":
        return "AWS_ACCESS_KEY_ID"
    return f"{prefix}_{word}"


# ===== the code =====

# The token beside the connection string: the one code SQL Server's uses too (domain/sql_server.py). A
# Fabric SQL endpoint is Azure SQL's kind of endpoint, so Microsoft's mssql-python reads it (the owner,
# 2026-11-17: "mssql for azure and sql server connections"; "odbc does not work on function apps").
SQL_ENDPOINT = (
    "\n"  # noqa: S608 (code: its names are quoted where they are made)
    + TOKEN_CODE
    + r'''

class Tds:
    """T-SQL on a Fabric SQL endpoint (a warehouse, or a lakehouse's SQL analytics endpoint): Microsoft's
    mssql-python (its own driver inside: nothing else installed), port 1433, signed in with the Entra
    token."""

    def __init__(self, server, database, token):
        self.server, self.database, self.token, self.sql = server, database, token, None

    def connection(self):
        if self.sql is None:
            import mssql_python  # a missing one: the import's own error, the app's Install prompt

            parts = {"Server": f"{self.server},1433", "Database": self.database, "Encrypt": "mandatory",
                     "TrustServerCertificate": "no"}
            text = "".join(f"{k}={v};" for k, v in parts.items())
            try:
                self.sql = mssql_python.connect(text, attrs_before={1256: token_struct(self.token())})
            except Exception as error:  # the driver's own error class
                said = str(error)
                raise LakeError(f"Fabric's SQL endpoint refused: {said.splitlines()[0][:300]}") from None
        return self.sql

    def cursor(self):
        return self.connection().cursor()

    def tables(self):
        cur = self.cursor()
        cur.execute("SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
                    "ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION")
        return [tuple(r) for r in cur.fetchall()]

    def rows(self, schema, table, limit, columns, filters):
        name = f"[{schema.replace(']', ']]')}].[{table.replace(']', ']]')}]"
        known = [r[2] for r in self.tables() if r[0].casefold() == schema.casefold()
                 and r[1].casefold() == table.casefold()]
        if not known:
            raise LakeError(f"The SQL endpoint has no table {schema}.{table}.")
        by_name = {k.casefold(): k for k in known}
        picked = [by_name[str(c).casefold()] for c in columns or [] if str(c).casefold() in by_name]
        listed = ", ".join(f"[{c}]" for c in picked) if picked else "*"
        where, params = where_of(filters, known)
        where = re.sub(r'"((?:[^"]|"")*)"', lambda m: "[" + m.group(1).replace('""', '"') + "]", where)
        clause = f" WHERE {where}" if where else ""
        cur = self.cursor()
        cur.execute(f"SELECT COUNT_BIG(*) FROM {name}{clause}", *params)
        total = int(cur.fetchall()[0][0])
        top = f"TOP {int(limit)} " if limit is not None else ""
        cur.execute(f"SELECT {top}{listed} FROM {name}{clause}", *params)
        names = [d[0] for d in cur.description]
        found = [dict(zip(names, r)) for r in cur.fetchall()]
        import pyarrow as pa

        result = pa.Table.from_pylist(found) if found else pa.table({n: [] for n in names})
        return result.replace_schema_metadata({b"sab_read": b"sql"}), total
'''
)

_KINDS = r'''

class DeltaLake(Lake):
    """Delta tables wherever they are: every folder under the root holding a _delta_log, to a depth."""

    mode = "delta"

    def __init__(self, store, depth=4):
        super().__init__(store, "Delta Lake")
        self.depth = int(depth)

    def entries(self, path="", depth=MAX_DEPTH):
        return self.store.walk(path, min(depth, self.depth + 1))

    def none_words(self):
        return f"no folder holding a _delta_log, to a depth of {self.depth}"


class DataLake(Lake):
    """A container (and folder) of Azure Data Lake Storage: its Parquet, CSV and JSON files, Delta
    folders and hive-partitioned folders, one table each."""

    mode = "files"


class OneLake(Lake):
    """A Microsoft Fabric lakehouse (its Delta tables under Tables/, its files under Files/) or warehouse
    (T-SQL on its SQL endpoint). `sql_endpoint`: the SQL endpoint's address, for T-SQL (%%sql)."""

    def __init__(self, workspace, item, token, sql_endpoint="", sql_token=None):
        item = str(item).strip()
        if not re.search(r"\.(Lakehouse|Warehouse)$", item, re.I):
            raise LakeError(f"Name the item with its kind: Sales.Lakehouse or Finance.Warehouse, not {item!r}.")
        super().__init__(AzureStore("onelake", workspace, item, token, domain="dfs.fabric.microsoft.com"), "OneLake")
        self.warehouse = item.lower().endswith(".warehouse")
        self.tds = Tds(sql_endpoint, item.rsplit(".", 1)[0], sql_token) if sql_endpoint else None
        if self.warehouse and self.tds is None:
            raise LakeError("A warehouse's tables are read by T-SQL: fill in its SQL endpoint (the warehouse's "
                            "settings, SQL connection string).")

    def tables(self):
        if self.found is None and self.warehouse:
            seen = {}
            for schema, table, _, _ in self.tds.tables():
                seen.setdefault((schema, table), {"schema": schema, "table": table, "kind": "sql", "format": "sql",
                                                  "path": "", "files": [], "size": 0, "partitions": []})
            self.found = list(seen.values())
        if self.found is None:
            found = []
            for t in discover(self.entries("Tables", 2), "delta"):
                t["schema"] = "/".join(p for p in t["schema"].split("/")[1:] if p)  # below Tables/
                found.append(t)
            files = [e for e in self.entries("Files") if e["path"].startswith("Files/")]
            found += discover(files, "files")
            self.found = found[:MAX_TABLES]
            if not self.found:
                raise LakeError(f"{self.store.where()} holds no tables under Tables/ or files under Files/.")
        return [dict(t) for t in self.found]

    def rows(self, table, schema="", limit=None, columns=None, filters=None, frame=False):
        if self.warehouse:
            t = self.table(table, schema)
            result, total = self.tds.rows(t["schema"], t["table"], limit, columns, filters)
            return (result.to_pandas() if frame else result), total
        return super().rows(table, schema, limit, columns, filters, frame)

    def describe(self, t):
        if t["kind"] == "sql":
            columns = [(c, k) for s, n, c, k in self.tds.tables() if (s, n) == (t["schema"], t["table"])]
            return columns, "warehouse table"
        return super().describe(t)

    def cursor(self):
        """T-SQL on the SQL endpoint when there is one, else DuckDB with every table a view."""
        if self.tds is not None:
            return self.tds.cursor()
        return super().cursor()
'''

_HEAD = entra.IMPORTS.replace("import time\n", "import struct\nimport time\n") + "\nimport duckdb\n"
_BODY = entra.COMMON + code.STORES + code.DELTA + code.WRITER + code.READER
_ENTRA = {"you": entra.YOU, "managed": entra.MANAGED, "app": entra.APP, "mfa": entra.MFA}

# ===== OneLake =====

_ONELAKE_PLACE = """
# The workspace (its name or id), and the item: a lakehouse (Sales.Lakehouse) or a warehouse
# (Finance.Warehouse). For T-SQL (a warehouse, or a lakehouse's SQL analytics endpoint): the SQL
# endpoint's address from the item's settings (SQL connection string).
workspace = "My Workspace"
item = "Sales.Lakehouse"
sql_endpoint = ""
"""


def _onelake(way: str) -> str:
    return (
        _HEAD + _ONELAKE_PLACE + _ENTRA[way] + _BODY + SQL_ENDPOINT + _KINDS + "\n\n"
        'storage = Token(sign_in, "https://storage.azure.com/.default")\n'
        'warehouse = Token(sign_in, "https://database.windows.net/.default")\n'
        "conn = OneLake(workspace, item, storage, sql_endpoint, warehouse)\n"
    )


# ===== Data Lake =====

_DATALAKE_PLACE = """
# The storage account, its container, and a folder in it ("" for the container's root).
account = "my-storage-account"
container = "my-container"
folder_in_container = ""
"""
_ACCOUNT_KEY = """
# The storage account's access key, from a key vault (it signs a short-lived read-only SAS here).
account_key = secret("account key")
"""
_SAS = """
# A SAS token for the container (read and list), from a key vault.
sas_token = secret("sas token")
"""


def _datalake(way: str) -> str:
    if way == "key":
        sign_in, made = _ACCOUNT_KEY, "AzureStore(account, container, folder_in_container, key=account_key)"
    elif way == "sas":
        sign_in, made = _SAS, "AzureStore(account, container, folder_in_container, sas=sas_token)"
    else:
        sign_in = _ENTRA[way]
        made = 'AzureStore(account, container, folder_in_container, Token(sign_in, "https://storage.azure.com/.default"))'
    return _HEAD + _DATALAKE_PLACE + sign_in + _BODY + _KINDS + f"\n\nconn = DataLake({made})\n"


# ===== Delta Lake =====

_DELTA_LOCAL = """
# A folder on this computer (or a share) holding Delta tables, looked into to a depth.
root = r"C:\\lake"
depth = 4
"""
_DELTA_AZURE = """
# Delta tables in Azure Data Lake Storage or OneLake: abfss://<container>@<account>.dfs.core.windows.net/<path>
# (OneLake: abfss://<workspace>@onelake.dfs.fabric.microsoft.com/<item>/Tables), looked into to a depth.
root = "abfss://my-container@my-account.dfs.core.windows.net/lake"
depth = 4
"""
_DELTA_S3 = """
# Delta tables in Amazon S3: s3://<bucket>/<path>, looked into to a depth.
root = "s3://my-bucket/lake"
depth = 4
region = "us-east-1"
"""
_S3_KEY = """
# An access key: its id here, its secret from a key vault.
access_key_id = "my-access-key-id"
aws_secret_access_key = secret("aws secret access key")
"""
_S3_PROFILE = """
# A profile of this computer's AWS configuration (~/.aws).
profile = "default"
"""


def _delta(way: str) -> str:
    if way == "local":
        place, made = _DELTA_LOCAL, "LocalStore(root)"
    elif way == "s3key":
        place = _DELTA_S3 + _S3_KEY
        made = "store_of(root, key_id=access_key_id, secret_key=aws_secret_access_key, region=region)"
    elif way == "s3profile":
        place, made = _DELTA_S3 + _S3_PROFILE, "store_of(root, region=region, profile=profile)"
    elif way == "key":
        place, made = _DELTA_AZURE + _ACCOUNT_KEY, "store_of(root, key=account_key)"
    else:
        place = _DELTA_AZURE + _ENTRA[way]
        made = 'store_of(root, Token(sign_in, "https://storage.azure.com/.default"))'
    return _HEAD + place + _BODY + _KINDS + f"\n\nconn = DeltaLake({made}, depth)\n"


ONELAKE_YOU: str = _onelake("you")
DATALAKE_YOU: str = _datalake("you")
DELTA_LOCAL: str = _delta("local")

# The app registration first: it runs here and on an Azure Function App or a hosted Streamlit app alike; as
# you (this machine's only, domain/portability.py) last (the owner, 2026-11-17: "we want to advise against
# any connectors that only work locally"). A saved connection keeps its own code.
_ENTRA_WAYS: tuple[tuple[str, str, str], ...] = (
    (entra.SIGN_INS[2][0], entra.APP_MARK, "app"),
    (entra.SIGN_INS[1][0], entra.MANAGED_MARK, "managed"),
    (entra.SIGN_INS[0][0], entra.YOU_MARK, "you"),
    (entra.MFA_LABEL, entra.MFA_MARK, "mfa"),
)
ONELAKE_SIGN_INS: tuple[tuple[str, str, str], ...] = tuple(
    (label, mark, _onelake(way)) for label, mark, way in _ENTRA_WAYS
)
DATALAKE_SIGN_INS: tuple[tuple[str, str, str], ...] = (
    *((label, mark, _datalake(way)) for label, mark, way in _ENTRA_WAYS),
    ("Account key, from a key vault", 'account_key = secret("account key")', _datalake("key")),
    ("SAS token, from a key vault", 'sas_token = secret("sas token")', _datalake("sas")),
)
DELTA_SIGN_INS: tuple[tuple[str, str, str], ...] = (
    *((f"Azure: {label[:1].lower()}{label[1:]}", mark, _delta(way)) for label, mark, way in _ENTRA_WAYS),
    ("Azure: account key, from a key vault", 'account_key = secret("account key")', _delta("key")),
    (
        "Amazon S3: access key, its secret from a key vault",
        "aws_secret_access_key = secret(",
        _delta("s3key"),
    ),
    ("A folder on this computer", "# A folder on this computer", _delta("local")),
    ("Amazon S3: a profile on this computer", 'profile = "', _delta("s3profile")),
)
