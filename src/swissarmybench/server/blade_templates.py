"""Starter blades: the most used databases, a Power BI workspace, common file patterns, vaults and a few
analyses (plan, the owner's request).

Each template is a starting point the user edits on the save screen: the driver's import, the
connection with placeholders (`my-server`, `my_database`), `secret("password")` where a password goes,
the variable it makes, and a catalog command that lists the source's tables and columns. Database
catalogs are SQL in the source's own dialect; file catalogs are Python that reads only headers and a
few rows; vault templates make `get`, a function from a secret's name to its value, and most make
`names`, the secrets' names (the Connections window lists them to map to environment variables).

The packages each needs are read from the code itself (domain/blades.py), so the save screen can offer
to install them.
"""

from __future__ import annotations

from swissarmybench.domain import dataverse, keystores, lakes, sharepoint, sql_server
from swissarmybench.domain.blades import Template

# ===== catalog queries =====

INFORMATION_SCHEMA = """SELECT c.table_catalog, c.table_schema, c.table_name, t.table_type,
       c.column_name, c.data_type, c.is_nullable, c.ordinal_position
FROM information_schema.columns AS c
JOIN information_schema.tables AS t
  ON t.table_catalog = c.table_catalog
 AND t.table_schema = c.table_schema
 AND t.table_name = c.table_name
WHERE c.table_schema NOT IN ('information_schema', 'INFORMATION_SCHEMA', 'pg_catalog', 'sys')
ORDER BY c.table_schema, c.table_name, c.ordinal_position"""

SQLITE = """SELECT 'main' AS table_schema, m.name AS table_name, m.type AS table_type,
       p.name AS column_name, p.type AS data_type,
       CASE WHEN p."notnull" = 1 THEN 'NO' ELSE 'YES' END AS is_nullable,
       p.cid + 1 AS ordinal_position
FROM sqlite_master AS m
JOIN pragma_table_info(m.name) AS p
WHERE m.type IN ('table', 'view') AND m.name NOT LIKE 'sqlite_%'
ORDER BY m.name, p.cid"""

ORACLE = """SELECT c.owner, c.table_name, o.object_type AS table_type, c.column_name, c.data_type,
       c.nullable, c.column_id
FROM all_tab_columns c
JOIN all_objects o ON o.owner = c.owner AND o.object_name = c.table_name
                  AND o.object_type IN ('TABLE', 'VIEW')
WHERE c.owner NOT IN ('SYS', 'SYSTEM', 'XDB', 'MDSYS', 'CTXSYS', 'ORDSYS', 'OUTLN', 'DBSNMP',
                      'APEX_PUBLIC_USER')
ORDER BY c.owner, c.table_name, c.column_id"""

DB2 = """SELECT c.tabschema AS table_schema, c.tabname AS table_name,
       CASE t.type WHEN 'V' THEN 'VIEW' ELSE 'TABLE' END AS table_type,
       c.colname AS column_name, c.typename AS data_type,
       CASE c.nulls WHEN 'Y' THEN 'YES' ELSE 'NO' END AS is_nullable, c.colno + 1 AS ordinal_position
FROM syscat.columns c
JOIN syscat.tables t ON t.tabschema = c.tabschema AND t.tabname = c.tabname
WHERE c.tabschema NOT LIKE 'SYS%'
ORDER BY c.tabschema, c.tabname, c.colno"""

TERADATA = """SELECT c.DatabaseName AS table_schema, c.TableName AS table_name,
       CASE t.TableKind WHEN 'V' THEN 'VIEW' ELSE 'TABLE' END AS table_type,
       c.ColumnName AS column_name, c.ColumnType AS data_type, c.Nullable AS is_nullable,
       c.ColumnId AS ordinal_position
FROM DBC.ColumnsV c
JOIN DBC.TablesV t ON t.DatabaseName = c.DatabaseName AND t.TableName = c.TableName
WHERE c.DatabaseName NOT IN ('DBC', 'SYSLIB', 'SystemFe', 'SYSUDTLIB', 'TD_SYSFNLIB')
ORDER BY 1, 2, 7"""

SAP_HANA = """SELECT schema_name AS table_schema, table_name, 'TABLE' AS table_type, column_name,
       data_type_name AS data_type, is_nullable, position AS ordinal_position
FROM sys.table_columns
WHERE schema_name NOT LIKE '_SYS%' AND schema_name NOT IN ('SYS', 'SYSTEM')
UNION ALL
SELECT schema_name, view_name, 'VIEW', column_name, data_type_name, is_nullable, position
FROM sys.view_columns
WHERE schema_name NOT LIKE '_SYS%' AND schema_name NOT IN ('SYS', 'SYSTEM')
ORDER BY 1, 2, 7"""

VERTICA = """SELECT table_schema, table_name, 'TABLE' AS table_type, column_name, data_type,
       CASE WHEN is_nullable THEN 'YES' ELSE 'NO' END AS is_nullable, ordinal_position
FROM v_catalog.columns
UNION ALL
SELECT table_schema, table_name, 'VIEW', column_name, data_type, 'YES', ordinal_position
FROM v_catalog.view_columns
ORDER BY 1, 2, 7"""

BIGQUERY = """SELECT table_catalog, table_schema, table_name, column_name, data_type, is_nullable,
       ordinal_position
FROM `region-us`.INFORMATION_SCHEMA.COLUMNS
ORDER BY table_schema, table_name, ordinal_position"""

# Any ODBC source: pyodbc's own catalog call, which every ODBC driver answers.
ODBC_CATALOG = """[
    {
        "table_catalog": c.table_cat,
        "table_schema": c.table_schem,
        "table_name": c.table_name,
        "column_name": c.column_name,
        "data_type": c.type_name,
        "is_nullable": c.is_nullable,
        "ordinal_position": c.ordinal_position,
    }
    for c in conn.cursor().columns()
]"""

CLICKHOUSE_CATALOG = """conn.query_df(
    "SELECT database AS table_schema, table AS table_name, name AS column_name, type AS data_type, "
    "position AS ordinal_position FROM system.columns "
    "WHERE database NOT IN ('system', 'INFORMATION_SCHEMA', 'information_schema') "
    "ORDER BY database, table, position"
)"""


def _db(
    id: str,
    label: str,
    dialect: str,
    code: str,
    catalog: str,
    note: str = "",
    language: str = "sql",
    sign_ins: tuple[tuple[str, str, str], ...] = (),
    secrets_from: str = "",
) -> Template:
    return Template(
        id,
        label,
        "Databases",
        "sql",
        code,
        "conn",
        dialect,
        language,
        catalog,
        note=note,
        sign_ins=sign_ins,
        secrets_from=secrets_from,
    )


# SQL Server and Azure SQL (domain/sql_server.py): a SqlServer object signed in one of eight ways (the
# form's Sign in), its drivers found, its errors in plain words, its passing errors tried again, its reads
# typed exactly, its catalog from the system views.
# Microsoft's mssql-python only (nothing else installed); each starts with a sign-in that runs on an Azure
# Function App or a hosted Streamlit app as well as here (the owner, 2026-11-17).
SQLSERVER_LOGIN = sql_server.code("sql_login")
AZURE_APP = sql_server.code("app_secret", sql_server.AZURE_SERVER)
_SQLSERVER_NOTE = "Needs Microsoft's mssql-python (pip install mssql-python): no ODBC driver."


# ===== a Power BI workspace: its datasets (semantic models), read with DAX =====
#
# The connection is per workspace (the owner, 2026-11-15), as a database connection gives every
# schema: the code signs in, lists the workspace's datasets (GET .../groups/{workspace}/datasets) and
# sends DAX to any one of them through Power BI's Execute Queries request. A dataset is shaped like a
# database connection (cursor, execute, description, fetchall), so the catalog, Open as grid and DAX
# cells use it as they use a database. Its web requests are the standard library's: the app registration's
# sign-in needs no package at all (so the same code runs in an Azure Function as it is); only the
# browser sign-in needs Microsoft's azure-identity. Two environment variables move it to another
# cloud (or, in the tests, to a stand-in on this computer): POWERBI_API_URL and POWERBI_LOGIN_URL.

_POWERBI_IMPORTS = """import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
"""

_POWERBI_WHERE = """
# The workspace's id is in its address in Power BI: .../groups/<workspace id>/...
workspace_id = "my-workspace-id"
"""

_POWERBI_APP = '''
# Sign in as an app registration (service principal). Its values are read by name: from a key vault
# here; in an Azure Function, from the environment (the function app's Key Vault references).
tenant_id = TENANT
client_id = CLIENT
client_secret = secret("client secret")


def sign_in():
    """Microsoft's client credentials request: the token, and when it runs out."""
    login = os.environ.get("POWERBI_LOGIN_URL", "https://login.microsoftonline.com")
    form = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://analysis.windows.net/powerbi/api/.default",
    }
    sent = urllib.parse.urlencode(form).encode()
    answer = ask(f"{login}/{tenant_id}/oauth2/v2.0/token", sent, {}, "The sign-in")
    return answer["access_token"], time.time() + int(answer.get("expires_in", 3600))
'''

_POWERBI_BROWSER = '''
# Sign in as yourself, in a browser window: for trying a workspace by hand.
tenant_id = "organizations"
credential = InteractiveBrowserCredential(tenant_id=tenant_id)


def sign_in():
    """The token Microsoft gave for Power BI, and when it runs out."""
    found = credential.get_token("https://analysis.windows.net/powerbi/api/.default")
    return found.token, found.expires_on
'''

_POWERBI_CONNECTION = r'''

class PowerBIError(RuntimeError):
    """The sign-in or Power BI refused. The message is its own words, and what usually causes it."""


def ask(url, data, headers, what):
    """One web request (with `data`, a POST; without, a GET): its JSON answer."""
    request = urllib.request.Request(url, data, headers)
    try:
        with urllib.request.urlopen(request, timeout=120) as answer:
            return json.loads(answer.read())
    except urllib.error.HTTPError as refused:
        raise PowerBIError(why(what, refused.code, refused.read())) from None
    except urllib.error.URLError as error:
        host = urllib.parse.urlsplit(url).netloc
        raise PowerBIError(f"{what} could not reach {host}: {error.reason}") from None


def why(what, status, body):
    """A refusal in plain words: the service's own message, then what usually causes that status."""
    try:
        said = json.loads(body)
        error = said.get("error_description") or said.get("error") or said
    except (ValueError, AttributeError):
        error = body.decode("utf-8", "replace")[:300]
    if isinstance(error, dict):
        details = (error.get("pbi.error") or {}).get("details") or []
        words = [(d.get("detail") or {}).get("value") for d in details if d.get("code") == "DetailsMessage"]
        error = " ".join(w for w in words if w) or error.get("message") or error.get("code") or "no reason"
    hints = {
        401: "Check the tenant id, the client id and the client secret.",
        403: "The tenant must allow the Execute Queries request (Dataset Execute Queries REST API) and, "
        "for an app registration, service principals to use the Power BI APIs; the sign-in needs Read "
        "and Build permission on the dataset.",
        404: "Check the workspace id, and that this sign-in is a member of the workspace.",
        429: "Power BI takes 120 queries a minute from one user: wait a minute.",
    }
    first = str(error).strip().splitlines()[0] if str(error).strip() else "no reason"
    return f"{what} was refused ({status}): {first} {hints.get(status, '')}".strip()


def clean_names(keys):
    """Power BI names an answer's columns Sales[Amount] and [Total Sales]: Amount and Total Sales
    here. A name two tables share keeps its table."""
    bare = [re.sub(r"^.*?\[(.*)\]$", r"\1", key) for key in keys]
    return [name if bare.count(name) == 1 else key for key, name in zip(keys, bare)]


def dates(column):
    """Power BI writes a date as text (2026-01-31T00:00:00): a column of them becomes dates."""
    filled = [value for value in column if value is not None]
    written = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z?$")
    if not filled or not all(isinstance(value, str) and written.match(value) for value in filled):
        return column
    try:
        return [None if v is None else datetime.fromisoformat(v.rstrip("Z")[:26]) for v in column]
    except ValueError:
        return column


class Dataset:
    """One dataset (semantic model) of the workspace, read with DAX through Power BI's Execute
    Queries request. Shaped like a database connection (cursor, execute, description, fetchall), so
    a DAX cell, Open as grid and the catalog use it as they use a database."""

    # Power BI's limits for one query: 100,000 rows or 1,000,000 values (rows times columns),
    # whichever comes first, and 15 MB of data; one query in a request; 120 requests a minute for
    # each user. An answer cut at 15 MB cannot be told from a whole one by its size alone.
    MAX_ROWS = 100_000
    MAX_VALUES = 1_000_000

    def __init__(self, workspace, name, id):
        self.workspace, self.name, self.id = workspace, name, id
        self.description, self.rows = None, []

    def cursor(self):
        return self

    def close(self):
        pass

    def execute(self, dax):
        body = {"queries": [{"query": dax}], "serializerSettings": {"includeNulls": True}}
        answer = self.workspace.ask(f"/datasets/{self.id}/executeQueries", body, "The query")
        result = (answer.get("results") or [{}])[0]
        table = (result.get("tables") or [{}])[0]
        rows = table.get("rows") or []
        keys = list(dict.fromkeys(key for row in rows for key in row))
        stopped = answer.get("error") or result.get("error") or table.get("error")
        if isinstance(stopped, dict):
            stopped = stopped.get("message") or stopped.get("code")
        if len(rows) >= self.MAX_ROWS or len(rows) * len(keys) >= self.MAX_VALUES or (stopped and rows):
            raise PowerBIError(
                f"Power BI gives at most {self.MAX_ROWS:,} rows or {self.MAX_VALUES:,} values (rows times "
                f"columns) for one query. This answer reached that ({len(rows):,} rows of {len(keys)} "
                "columns), so it is not whole: ask for fewer rows or columns, or summarize in DAX."
                + (f" Power BI said: {stopped}" if stopped else "")
            )
        if stopped:
            raise PowerBIError(f"The query was refused: {stopped}")
        columns = [dates([row.get(key) for row in rows]) for key in keys]
        self.description = [(name, None, None, None, None, None, None) for name in clean_names(keys)]
        self.rows = list(zip(*columns))
        return self

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows


class PowerBI:
    """A Power BI workspace: every dataset (semantic model) in it, each read with DAX.

        conn.datasets()                        each dataset's name and id
        conn.dataset("Sales model")            one of them, by its name or its id
        conn.dataset("Sales model").cursor()   runs DAX on it, as a database's cursor runs SQL
        conn.cursor(dataset="Sales model")     the same
        conn.cursor()                          the workspace's one dataset (refused when it has several)
        conn.url                               the workspace's address in Power BI's REST API
        conn.access_token()                    this sign-in's token for that API (for actions such as
                                               a refresh: the starter pack's Power BI blades)
    """

    def __init__(self, workspace_id, sign_in):
        api = os.environ.get("POWERBI_API_URL", "https://api.powerbi.com")
        self.url = f"{api}/v1.0/myorg/groups/{workspace_id}"
        self.sign_in, self.token, self.expires = sign_in, "", 0.0
        self.found = None
        self.datasets()  # signs in and reaches the workspace now: Test means it

    def access_token(self):
        """The token, signed in again when it has five minutes or less to run."""
        if time.time() > self.expires - 300:
            self.token, self.expires = self.sign_in()
        return self.token

    def ask(self, path, body, what):
        headers = {"Authorization": f"Bearer {self.access_token()}", "Content-Type": "application/json"}
        return ask(self.url + path, None if body is None else json.dumps(body).encode(), headers, what)

    def datasets(self):
        """Each dataset's name and id, listed once. Two with one name are told apart by their ids."""
        if self.found is None:
            listed = self.ask("/datasets", None, "Listing the workspace's datasets").get("value") or []
            names = [str(d.get("name") or d["id"]) for d in listed]
            self.found = [
                {"name": n if names.count(n) == 1 else f"{n} ({str(d['id'])[:8]})", "id": str(d["id"])}
                for d, n in zip(listed, names)
            ]
        return [dict(d) for d in self.found]

    def names(self):
        return ", ".join(d["name"] for d in self.datasets()) or "none"

    def dataset(self, name):
        wanted = str(name).strip().lower()
        for d in self.datasets():
            if wanted in (d["name"].lower(), d["id"].lower()):
                return Dataset(self, d["name"], d["id"])
        raise PowerBIError(f"The workspace has no dataset {str(name)!r}. It has: {self.names()}.")

    def cursor(self, dataset=None):
        if dataset is None:
            found = self.datasets()
            if len(found) != 1:
                raise PowerBIError(
                    f"The workspace has {len(found)} datasets: name the one to read, as "
                    f'conn.cursor(dataset="..."). It has: {self.names()}.'
                )
            dataset = found[0]["id"]
        return self.dataset(dataset)

    def close(self):
        pass


conn = PowerBI(workspace_id, sign_in)'''


def _powerbi(sign_in: str, imports: str = "") -> str:
    return _POWERBI_IMPORTS + imports + _POWERBI_WHERE + sign_in + _POWERBI_CONNECTION


def _powerbi_app(tenant: str, client: str) -> str:
    return _powerbi(_POWERBI_APP.replace("TENANT", tenant).replace("CLIENT", client))


POWERBI_VAULT = _powerbi_app('secret("tenant id")', 'secret("client id")')
POWERBI_TYPED = _powerbi_app('"my-tenant-id"', '"my-client-id"')
POWERBI_BROWSER = _powerbi(_POWERBI_BROWSER, "\nfrom azure.identity import InteractiveBrowserCredential\n")

# The workspace's datasets, each as a schema: its tables, columns (with types) and measures, each
# measure listed on its own table and marked. A dataset is asked the model's own description
# (INFO.VIEW) first; an older model's numbered form; then, for a sign-in that may not read the model's
# description, the columns' statistics (no types, no measures). Datasets are read one after another,
# at most MAX_DATASETS of them and for at most MAX_SECONDS; one that cannot be read (or was not
# reached) is a row with no table and the reason, which the tree shows on that dataset alone
# (adapters/catalogs.py keeps it as the schema's note).
POWERBI_CATALOG = """MAX_DATASETS = 25  # each takes two queries or more; Power BI takes 120 a minute
MAX_SECONDS = 200


def read(dataset, dax):
    dataset.execute(dax)
    columns = [d[0] for d in dataset.description]
    return [dict(zip(columns, row)) for row in dataset.fetchall()]


def own(table):  # the date tables Power BI makes by itself
    return str(table).startswith(("LocalDateTable_", "DateTableTemplate_"))


def described(dataset):
    try:
        found = read(dataset, "EVALUATE INFO.VIEW.COLUMNS()")
        columns = [(c["Table"], c["Name"], c.get("DataType") or "") for c in found]
        found = read(dataset, "EVALUATE INFO.VIEW.MEASURES()")
        measures = [(m["Table"], m["Name"], m.get("DataType") or "") for m in found]
    except (PowerBIError, KeyError):
        try:  # the numbered form: ids for tables, numbers for types
            types = {2: "Text", 6: "Integer", 8: "Double", 9: "DateTime", 10: "Decimal", 11: "Boolean"}
            tables = {t["ID"]: t["Name"] for t in read(dataset, "EVALUATE INFO.TABLES()")}
            columns = [
                (
                    tables.get(c["TableID"]),
                    c.get("ExplicitName") or c.get("InferredName"),
                    types.get(c.get("ExplicitDataType"), ""),
                )
                for c in read(dataset, "EVALUATE INFO.COLUMNS()")
                if c.get("Type") != 3  # 3: each table's hidden row number
            ]
            measures = [
                (tables.get(m["TableID"]), m["Name"], types.get(m.get("DataType"), ""))
                for m in read(dataset, "EVALUATE INFO.MEASURES()")
            ]
        except (PowerBIError, KeyError):
            found = read(dataset, "EVALUATE COLUMNSTATISTICS()")
            columns = [(c["Table Name"], c["Column Name"], "") for c in found]
            measures = []
    return [
        (table, name, kind)
        for table, name, kind in columns
        if table and name and not own(table) and not str(name).startswith("RowNumber-")
    ] + [
        (table, name, f"measure, {kind}" if kind else "measure")
        for table, name, kind in measures
        if table and name
    ]


def row(dataset, table="", column="", kind="", note=""):
    return {
        "schema_name": dataset,
        "table_name": table,
        "column_name": column,
        "data_type": kind,
        "description": note,
    }


started = time.time()
catalog = []
for at, found in enumerate(conn.datasets()):
    rows = []
    if at >= MAX_DATASETS:
        note = f"Not read: the catalog reads a workspace's first {MAX_DATASETS} datasets."
    elif time.time() - started > MAX_SECONDS:
        note = f"Not read: the catalog stops after {MAX_SECONDS} seconds."
    else:
        try:
            rows = described(conn.dataset(found["id"]))
            note = "" if rows else "It has no tables."
        except (PowerBIError, KeyError) as error:
            note = f"Could not be read: {error}"
    if note:
        catalog.append(row(found["name"], note=note))
    catalog += [row(found["name"], table, name, kind) for table, name, kind in rows]
if not catalog:
    raise PowerBIError("The workspace has no datasets this sign-in may read.")"""


DATABASES: tuple[Template, ...] = (
    _db(
        "sqlserver",
        "SQL Server",
        "sqlserver",
        SQLSERVER_LOGIN,
        sql_server.CATALOG,
        _SQLSERVER_NOTE,
        sign_ins=sql_server.sign_ins("sqlserver"),
    ),
    _db(
        "azuresql",
        "Azure SQL Database / Synapse",
        "sqlserver",
        AZURE_APP,
        sql_server.CATALOG,
        _SQLSERVER_NOTE,
        sign_ins=sql_server.sign_ins("azuresql"),
    ),
    _db(
        "postgres",
        "PostgreSQL",
        "postgres",
        """import psycopg

conn = psycopg.connect(
    host="my-server",
    port=5432,
    dbname="my_database",
    user="my_user",
    password=secret("password"),
)""",
        INFORMATION_SCHEMA,
    ),
    _db(
        "mysql",
        "MySQL",
        "mysql",
        """import pymysql

conn = pymysql.connect(
    host="my-server",
    port=3306,
    database="my_database",
    user="my_user",
    password=secret("password"),
)""",
        INFORMATION_SCHEMA.replace("'pg_catalog', 'sys'", "'mysql', 'performance_schema', 'sys'"),
    ),
    _db(
        "mariadb",
        "MariaDB",
        "mysql",
        """import mariadb

conn = mariadb.connect(
    host="my-server",
    port=3306,
    database="my_database",
    user="my_user",
    password=secret("password"),
)""",
        INFORMATION_SCHEMA.replace("'pg_catalog', 'sys'", "'mysql', 'performance_schema', 'sys'"),
    ),
    _db(
        "oracle",
        "Oracle",
        "oracle",
        """import oracledb

conn = oracledb.connect(
    user="my_user",
    password=secret("password"),
    dsn="my-server:1521/my_service",
)""",
        ORACLE,
        "oracledb's thin mode needs no Oracle client install.",
    ),
    _db(
        "sqlite",
        "SQLite",
        "sqlite",
        """import sqlite3
from pathlib import Path

path = Path(r"C:\\data\\my_database.sqlite")
# Read-only: a wrong path fails plainly instead of quietly making a new, empty database.
conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)""",
        SQLITE,
    ),
    _db(
        "duckdb",
        "DuckDB file",
        "duckdb",
        """import duckdb

conn = duckdb.connect(r"C:\\data\\my_database.duckdb", read_only=True)""",
        INFORMATION_SCHEMA,
    ),
    _db(
        "snowflake",
        "Snowflake",
        "snowflake",
        """import snowflake.connector

conn = snowflake.connector.connect(
    account="my_account",
    user="my_user",
    password=secret("password"),  # single sign-on in a browser instead works on this computer only
    warehouse="my_warehouse",
    database="MY_DATABASE",
)""",
        INFORMATION_SCHEMA,
    ),
    _db(
        "bigquery",
        "Google BigQuery",
        "other",
        """from google.cloud import bigquery
from google.cloud.bigquery import dbapi

conn = dbapi.connect(bigquery.Client(project="my-project"))""",
        BIGQUERY,
        "Signs in with `gcloud auth application-default login`. Change region-us to your region.",
    ),
    _db(
        "redshift",
        "Amazon Redshift",
        "postgres",
        """import redshift_connector

conn = redshift_connector.connect(
    host="my-cluster.abc123.us-east-1.redshift.amazonaws.com",
    database="my_database",
    user="my_user",
    password=secret("password"),
)""",
        INFORMATION_SCHEMA,
    ),
    _db(
        "databricks",
        "Databricks",
        "other",
        """from databricks import sql

conn = sql.connect(
    server_hostname="adb-1234567890.12.azuredatabricks.net",
    http_path="/sql/1.0/warehouses/my_warehouse",
    access_token=secret("token"),
)""",
        INFORMATION_SCHEMA,
    ),
    _db(
        "db2",
        "IBM Db2",
        "other",
        """import ibm_db_dbi

conn = ibm_db_dbi.connect(
    "DATABASE=my_database;HOSTNAME=my-server;PORT=50000;PROTOCOL=TCPIP;"
    "UID=my_user;PWD=" + secret("password") + ";"
)""",
        DB2,
    ),
    _db(
        "teradata",
        "Teradata",
        "other",
        """import teradatasql

conn = teradatasql.connect(host="my-server", user="my_user", password=secret("password"))""",
        TERADATA,
    ),
    # Two ways to sign in (domain/keystores.py): the user's password, or a client certificate from a
    # keystore file (PKCS#12, JKS or JCEKS) whose path may come from an environment variable.
    _db(
        "trino",
        "Trino / Presto",
        "trino",
        keystores.TRINO_BASIC,
        INFORMATION_SCHEMA,
        sign_ins=keystores.SIGN_INS,
    ),
    _db(
        "clickhouse",
        "ClickHouse",
        "other",
        """import clickhouse_connect

conn = clickhouse_connect.get_client(
    host="my-server",
    username="my_user",
    password=secret("password"),
)""",
        CLICKHOUSE_CATALOG,
        language="python",
    ),
    _db(
        "saphana",
        "SAP HANA",
        "other",
        """from hdbcli import dbapi

conn = dbapi.connect(address="my-server", port=30015, user="my_user", password=secret("password"))""",
        SAP_HANA,
    ),
    _db(
        "vertica",
        "Vertica",
        "other",
        """import vertica_python

conn = vertica_python.connect(
    host="my-server",
    port=5433,
    database="my_database",
    user="my_user",
    password=secret("password"),
)""",
        VERTICA,
    ),
    _db(
        "sybase",
        "SAP ASE (Sybase)",
        "sqlserver",
        """import pyodbc

conn = pyodbc.connect(
    "Driver={Adaptive Server Enterprise};Server=my-server;Port=5000;"
    "Database=my_database;UID=my_user;PWD=" + secret("password") + ";"
)""",
        ODBC_CATALOG,
        "Needs SAP's ASE ODBC driver.",
        language="python",
    ),
    _db(
        "access",
        "Microsoft Access",
        "other",
        """import pyodbc

conn = pyodbc.connect(
    r"Driver={Microsoft Access Driver (*.mdb, *.accdb)};"
    r"DBQ=C:\\data\\my_database.accdb;"
)""",
        ODBC_CATALOG,
        "Needs the Microsoft Access Database Engine (Windows).",
        language="python",
    ),
    _db(
        "odbc",
        "Any ODBC data source",
        "other",
        """import pyodbc

conn = pyodbc.connect("DSN=my_data_source")""",
        ODBC_CATALOG,
        "Uses a data source set up in the ODBC Data Source Administrator.",
        language="python",
    ),
    _db(
        "powerbi",
        "Power BI workspace",
        "dax",
        POWERBI_VAULT,
        POWERBI_CATALOG,
        "",
        language="python",
        sign_ins=(
            ("App registration, from a key vault", "tenant_id = secret(", POWERBI_VAULT),
            ("App registration, ids typed here", 'client_id = "', POWERBI_TYPED),
            ("Browser sign-in, as yourself", "InteractiveBrowserCredential", POWERBI_BROWSER),
        ),
        secrets_from="vault",
    ),
    # A Dataverse environment (domain/dataverse.py): its tables listed and read on its read-only SQL
    # endpoint (TDS; the owner, 2026-11-17), SQL there too; signed in as you, a managed identity or an
    # app registration whose client secret comes from a key vault only.
    _db(
        dataverse.TEMPLATE,
        "Dataverse",
        dataverse.DIALECT,
        dataverse.APP,
        dataverse.SQL_CATALOG,
        "",
        language="sql",
        sign_ins=dataverse.SIGN_INS,
        secrets_from=dataverse.VAULT_ONLY,
    ),
)

# Lakes and SharePoint (domain/lakes.py): tables the connection's own code lists and reads (its catalog
# `conn.catalog()`, its read lakes.READ), each its own dialect; one sign-in (domain/entra.py).


def _lake(id: str, sign_ins: tuple[tuple[str, str, str], ...], note: str = "") -> Template:
    return Template(
        id,
        lakes.LABELS[id],
        lakes.GROUP,
        "sql",
        sign_ins[0][2],
        "conn",
        id,
        "python",
        lakes.CATALOG,
        note=note,
        sign_ins=sign_ins,
    )


LAKES: tuple[Template, ...] = (
    _lake(lakes.ONELAKE, lakes.ONELAKE_SIGN_INS),
    _lake(lakes.DATALAKE, lakes.DATALAKE_SIGN_INS),
    _lake(lakes.DELTA, lakes.DELTA_SIGN_INS),
    _lake(lakes.SHAREPOINT, sharepoint.LISTS_SIGN_INS),
    _lake(lakes.SHAREPOINT_DOCS, sharepoint.DOCS_SIGN_INS),
)

FILES: tuple[Template, ...] = (
    Template(
        "csv",
        "A CSV file",
        "Files",
        "other",
        """from pathlib import Path

path = Path(r"C:\\data\\orders.csv")""",
        "path",
        catalog_language="python",
        catalog_command="""import pandas as pd

sample = pd.read_csv(path, nrows=1000)
[
    {"table_schema": path.parent.name, "table_name": path.stem,
     "column_name": str(name), "data_type": str(kind)}
    for name, kind in sample.dtypes.items()
]""",
    ),
    Template(
        "excel",
        "An Excel workbook",
        "Files",
        "other",
        """from pathlib import Path

path = Path(r"C:\\data\\budget.xlsx")""",
        "path",
        catalog_language="python",
        catalog_command="""import pandas as pd

sheets = pd.read_excel(path, sheet_name=None, nrows=200)  # every sheet, its first rows only
[
    {"table_schema": path.stem, "table_name": sheet, "column_name": str(name), "data_type": str(kind)}
    for sheet, frame in sheets.items()
    for name, kind in frame.dtypes.items()
]""",
    ),
    Template(
        "parquet",
        "A Parquet file",
        "Files",
        "other",
        """from pathlib import Path

path = Path(r"C:\\data\\events.parquet")""",
        "path",
        catalog_language="python",
        catalog_command="""import pyarrow.parquet as pq

[
    {"table_schema": path.parent.name, "table_name": path.stem,
     "column_name": f.name, "data_type": str(f.type)}
    for f in pq.read_schema(path)
]""",
    ),
    Template(
        "json",
        "A JSON file",
        "Files",
        "other",
        """from pathlib import Path

path = Path(r"C:\\data\\records.json")""",
        "path",
        catalog_language="python",
        catalog_command="""import pandas as pd

sample = pd.read_json(path).head(1000)
[
    {"table_schema": path.parent.name, "table_name": path.stem,
     "column_name": str(name), "data_type": str(kind)}
    for name, kind in sample.dtypes.items()
]""",
    ),
    Template(
        "folder",
        "A folder of files",
        "Files",
        "other",
        """from pathlib import Path

folder = Path(r"C:\\data\\exports")""",
        "folder",
        catalog_language="python",
        catalog_command="""import pandas as pd
import pyarrow.parquet as pq


def columns_of(file):
    if file.suffix.lower() == ".parquet":
        return [(f.name, str(f.type)) for f in pq.read_schema(file)]
    if file.suffix.lower() in (".xlsx", ".xlsm"):
        return [(str(n), str(k)) for n, k in pd.read_excel(file, nrows=200).dtypes.items()]
    return [(str(n), str(k)) for n, k in pd.read_csv(file, nrows=1000).dtypes.items()]


[
    {"table_schema": folder.name, "table_name": file.name, "column_name": name, "data_type": kind}
    for file in sorted(folder.iterdir())
    if file.suffix.lower() in (".csv", ".txt", ".parquet", ".xlsx", ".xlsm")
    for name, kind in columns_of(file)
]""",
    ),
)


# An Azure Key Vault signs in as you or as the managed identity of the Azure app it runs in (the form's
# Sign in; docs/ideas.md, 2026-11-15). Nothing is entered on this computer to open it: an app
# registration lives IN the vault, as entries other connections use (Power BI's). The exported script
# reads the same vault with the same sign-in, by Azure's own REST calls (no azure-identity needed
# there): domain/script_export.py.
_AZURE_VAULT_READ = """
client = SecretClient(vault_url="https://my-vault.vault.azure.net", credential=credential)


def names():
    return [p.name for p in client.list_properties_of_secrets() if p.enabled]


def get(name):
    return client.get_secret(name).value"""

AZURE_VAULT_YOU = (
    "from azure.identity import DefaultAzureCredential\n"
    "from azure.keyvault.secrets import SecretClient\n\n"
    "credential = DefaultAzureCredential()\n" + _AZURE_VAULT_READ
)
AZURE_VAULT_MANAGED = (
    "from azure.identity import ManagedIdentityCredential\n"
    "from azure.keyvault.secrets import SecretClient\n\n"
    "# The managed identity of the Azure app this runs in (a Function App, App Service or VM). A\n"
    "# user-assigned identity: its client id here.\n"
    'client_id = ""\n'
    "credential = ManagedIdentityCredential(client_id=client_id or None)\n" + _AZURE_VAULT_READ
)


def _vault(id: str, label: str, code: str, note: str = "") -> Template:
    return Template(
        id,
        label,
        "Vaults",
        "vault",
        code,
        "get",
        vault_mapping=(("WAREHOUSE_PASSWORD", "warehouse-password"),),
        note=note,
    )


VAULTS: tuple[Template, ...] = (
    Template(
        "azure_key_vault",
        "Azure Key Vault",
        "Vaults",
        "vault",
        AZURE_VAULT_YOU,
        "get",
        vault_mapping=(("WAREHOUSE_PASSWORD", "warehouse-password"),),
        note="Signs in as you here, or as the managed identity of the Azure app it runs in.",
        sign_ins=(
            ("As you (Azure CLI, VS Code or Windows sign-in)", "DefaultAzureCredential", AZURE_VAULT_YOU),
            (
                "Managed identity (in Azure: a Function App, App Service or VM)",
                "ManagedIdentityCredential",
                AZURE_VAULT_MANAGED,
            ),
        ),
    ),
    _vault(
        "aws_secrets_manager",
        "AWS Secrets Manager",
        """import boto3

client = boto3.client("secretsmanager", region_name="us-east-1")


def names():
    pages = client.get_paginator("list_secrets").paginate()
    return [s["Name"] for page in pages for s in page["SecretList"]]


def get(name):
    return client.get_secret_value(SecretId=name)["SecretString"]""",
        "Uses your AWS profile (`aws configure` or `aws sso login`).",
    ),
    _vault(
        "aws_parameter_store",
        "AWS Systems Manager Parameter Store",
        """import boto3

client = boto3.client("ssm", region_name="us-east-1")


def names():
    pages = client.get_paginator("describe_parameters").paginate()
    return [p["Name"] for page in pages for p in page["Parameters"]]


def get(name):
    return client.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]""",
    ),
    _vault(
        "google_secret_manager",
        "Google Secret Manager",
        """from google.cloud import secretmanager

client = secretmanager.SecretManagerServiceClient()
project = "my-project"


def names():
    return [s.name.rsplit("/", 1)[-1] for s in client.list_secrets(parent=f"projects/{project}")]


def get(name):
    path = f"projects/{project}/secrets/{name}/versions/latest"
    return client.access_secret_version(name=path).payload.data.decode()""",
        "Signs in with `gcloud auth application-default login`.",
    ),
    _vault(
        "hashicorp_vault",
        "HashiCorp Vault",
        """import os

import hvac

client = hvac.Client(url="https://vault.example.com:8200", token=os.environ.get("VAULT_TOKEN"))


def get(name):
    path, _, key = name.partition("#")  # "app/warehouse#password": a key inside a KV v2 secret
    data = client.secrets.kv.v2.read_secret_version(path=path)["data"]["data"]
    return data[key or "value"]""",
    ),
    _vault(
        "onepassword",
        "1Password",
        """import subprocess


def get(name):
    # name is a secret reference, such as "op://Private/Warehouse/password" (1Password's CLI, signed in).
    return subprocess.run(["op", "read", name], capture_output=True, text=True, check=True).stdout.strip()""",
        "Needs the 1Password CLI (`op`), signed in.",
    ),
    _vault(
        "dotenv",
        "A .env file",
        """from dotenv import dotenv_values

values = dotenv_values(r"C:\\projects\\my_project\\.env")


def names():
    return list(values)


def get(name):
    return values.get(name)""",
    ),
    _vault(
        "os_vault",
        "Windows Credential Manager / macOS Keychain",
        """import keyring

service = "my-service"


def get(name):
    return keyring.get_password(service, name)""",
    ),
)

OTHER: tuple[Template, ...] = (
    Template(
        "blank",
        "Blank (any code)",
        "Other",
        "other",
        """import requests

session = requests.Session()
session.headers["Authorization"] = "Bearer " + secret("token")""",
        "session",
    ),
)

# ===== a connection from your own Python (domain/python_connections.py) =====
# Three boxes: Connect makes `conn`; List the tables returns its catalog; Read a table returns a
# table's rows. The starter is a made-up web service's client, standard library only, so it runs
# as it is once its two variables have values.

PYTHON_CONNECT = """import json
import os
import urllib.request


class Api:
    def __init__(self, url, key):
        self.url, self.key = url.rstrip("/"), key

    def get(self, path):
        request = urllib.request.Request(self.url + path, headers={"X-Api-Key": self.key})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)


conn = Api(os.environ["ORDERS_API_URL"], os.environ["ORDERS_API_KEY"])"""

PYTHON_TABLES = """[
    {"schema": "api", "table": table["name"], "column": column["name"], "type": column["type"]}
    for table in conn.get("/tables")
    for column in table["columns"]
]"""

PYTHON_READ = """found = conn.get(f"/tables/{table}/rows" + (f"?limit={limit}" if limit else ""))
found["rows"], found["total"]"""

PYTHON: tuple[Template, ...] = (
    Template(
        "python",
        "Python (your own code)",
        "Your own code",
        "other",
        PYTHON_CONNECT,
        "conn",
        catalog_language="python",
        catalog_command=PYTHON_TABLES,
        read_command=PYTHON_READ,
    ),
)

# ===== your own analyses (the Analyze menu) =====
# A function of the grid's rows (a pandas DataFrame, as the grid shows them) and, if it takes a second
# argument, the selected columns. It returns markdown, a table, a figure, or a list or dict of them.

ANALYSES: tuple[Template, ...] = (
    Template(
        "summary",
        "Summary of every column",
        "Analyses",
        "analysis",
        """import pandas as pd


def analyze(df: pd.DataFrame) -> list:
    summary = df.describe(include="all").transpose().reset_index(names="column")
    note = f"## {len(df):,} rows, {len(df.columns)} columns\\n\\nCounts, means and spreads of each column."
    return [note, summary]""",
        "analyze",
        note="Runs on the grid's rows as it shows them; its result can go to Visualizations.",
    ),
    Template(
        "pareto",
        "Pareto: which values make 80%",
        "Analyses",
        "analysis",
        """import pandas as pd


def analyze(df: pd.DataFrame, columns: list[str]) -> list:
    column = columns[0] if columns else df.columns[0]
    counts = df[column].value_counts().rename_axis(column).reset_index(name="rows")
    counts["share"] = counts["rows"] / counts["rows"].sum()
    counts["running share"] = counts["share"].cumsum()
    few = int((counts["running share"] < 0.8).sum()) + 1
    note = (
        f"## {column}: {few} of {len(counts):,} values make 80% of the rows\\n\\n"
        "The values, commonest first, with their running share."
    )
    return [note, counts.head(50)]""",
        "analyze",
        note="Select a column first; without one it takes the first.",
    ),
    Template(
        "correlations",
        "Correlations of the number columns",
        "Analyses",
        "analysis",
        """import pandas as pd


def analyze(df: pd.DataFrame) -> dict:
    numbers = df.select_dtypes("number")
    table = numbers.corr().round(3).reset_index(names="column")
    return {
        "title": "Correlations",
        "markdown": "Pearson's r between every pair of number columns: 1 moves together, -1 opposite.",
        "table": table,
    }""",
        "analyze",
    ),
)

TEMPLATES: tuple[Template, ...] = (*DATABASES, *LAKES, *FILES, *PYTHON, *VAULTS, *OTHER, *ANALYSES)
BY_ID: dict[str, Template] = {t.id: t for t in TEMPLATES}
