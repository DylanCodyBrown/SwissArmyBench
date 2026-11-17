"""A Dataverse environment as a connection (the owner, 2026-11-16: "Add Dataverse to 0.0.7"): its tables
read through the Web API, SQL through its read-only SQL endpoint.

It is a starter (server/blade_templates.py DATAVERSE), modelled on the Power BI workspace: code that
signs in and makes `conn`, a `Dataverse` object written here as text, standard library only, so the
same code runs in the app's child process, a Workbench kernel and an exported script (an Azure
Function's timer) as it is:

- reading a table: the Web API's OData (`$select`, `$filter`, `$top`, paging by `@odata.nextLink`,
  the formatted values header, so a choice column reads as its labels). It works in every
  environment, with no admin setting: Open as grid, `sab.read` and the catalog's first line use it
  (READ below, the connection's own Read a table);
- the catalog: the Web API's metadata (`EntityDefinitions` with their `Attributes`): one schema (dbo,
  as the SQL endpoint names it), each table with its display name, each column with its type and
  display name (CATALOG);
- SQL: `conn.cursor()` on the read-only SQL endpoint (TDS, `<org>.crm.dynamics.com,5558`) through
  pyodbc and Microsoft's ODBC Driver 18, signed in with the same Entra token (as the SQL Server
  connection's Microsoft Entra sign-in does, but with the token itself). `%%sql <connection>` and
  `sab.sql` use it. When an environment's endpoint is off, the error says so in plain words
  (TDS_OFF) and the error panel offers the read instead;
- three ways to sign in (the form's Sign in): as you (azure-identity's DefaultAzureCredential: the
  Azure command line's sign-in, else a browser window; in Azure, the app's managed identity), a
  managed identity (the standard library's request, for an Azure Function), or an app registration
  whose client secret is a key vault's secret, never typed into the app (secrets_from VAULT_ONLY).

Two environment variables move the sign-in elsewhere (in the tests, to a stand-in on this computer):
DATAVERSE_LOGIN_URL (Microsoft's sign-in), and the managed identity's own IDENTITY_ENDPOINT and
IDENTITY_HEADER, which Azure sets. The environment's address itself is the form's Address.

This file is the text and a few rules about it. Pure: no I/O.
"""

from __future__ import annotations

import re

TEMPLATE: str = "dataverse"
DIALECT: str = "dataverse"
SCHEMA: str = "dbo"  # the one schema, as the SQL endpoint names its tables
SQL_PORT: int = 5558
# The form's passwords come only from a key vault (or an environment variable), never typed in.
VAULT_ONLY: str = "vault only"
# What the error says when the SQL endpoint is off (the error panel finds it by these words).
TDS_OFF_MARK: str = "SQL endpoint (TDS) is off"

# The connection's own Read a table, run after its code: (rows, total) for Open as grid, a frame for
# sab.read in a notebook (the app's read takes both).
READ: str = "conn.rows(table, limit=limit, frame=True)"
CATALOG: str = "catalog = conn.catalog()"
# Its tables on the read-only SQL endpoint (the owner, 2026-11-17: "Dataverse tds is the only method I
# like here"): the endpoint's own catalog, and a T-SQL SELECT to read one (domain/catalogs.py select_sql).
# The starter's default; a connection saved with CATALOG (the Web API's metadata) keeps working, and its
# card offers the switch (SQL_ENDPOINT_WORDS).
SQL_CATALOG: str = """SELECT TABLE_SCHEMA AS table_schema, TABLE_NAME AS table_name,
       'BASE TABLE' AS table_type, COLUMN_NAME AS column_name, DATA_TYPE AS data_type,
       IS_NULLABLE AS is_nullable, ORDINAL_POSITION AS ordinal_position
FROM INFORMATION_SCHEMA.COLUMNS
ORDER BY TABLE_NAME, ORDINAL_POSITION"""
WEB_API_WORDS: str = "Web API (switch to the SQL endpoint)"


def on_sql_endpoint(catalog_language: str | None) -> bool:
    """A Dataverse connection whose tables are listed and read on its SQL endpoint (its catalog is SQL)."""
    return catalog_language == "sql"


def is_dataverse(dialect: str | None) -> bool:
    return dialect == DIALECT


def tds_off(message: str) -> bool:
    """Whether an error is the SQL endpoint being off in that environment."""
    return TDS_OFF_MARK in message


_FROM = re.compile(r"\b(?:FROM|JOIN)\s+(?:\[?dbo\]?\.)?\[?([A-Za-z_][A-Za-z0-9_]*)\]?", re.IGNORECASE)


def read_instead(connection: str, sql: str) -> str:
    """The line that reads the table a query names through the Web API instead, for when the SQL
    endpoint is off: `account = sab.read("Sales CRM", "account")` (the first table it names)."""
    found = _FROM.search(sql)
    table = found.group(1).lower() if found else "account"
    name = table if table.isidentifier() else "rows"
    return f"{name} = sab.read({_text(connection)}, {_text(table)})"


def _text(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ===== the connection's code, as text =====

_IMPORTS = """import json
import os
import re
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
"""

_WHERE = """
# The environment's address (Power Apps: Settings, Session details, Instance url).
url = "https://your-org.crm.dynamics.com"
"""

_YOU = '''
# Sign in as yourself: the Azure command line's sign-in (az login), else a browser window. In Azure (a
# Function App), the app's own managed identity.
credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)


def sign_in(scope):
    """The token Microsoft gave for this environment, and when it runs out."""
    found = credential.get_token(scope)
    return found.token, found.expires_on
'''

_MANAGED = '''
# Sign in as the managed identity of the Azure app this runs in (a Function App, App Service or VM),
# added to the environment as an application user. A user-assigned identity: its client id here.
client_id = ""


def sign_in(scope):
    """The managed identity's token for this environment (Azure's own local request), and when it
    runs out."""
    query = {"resource": scope.removesuffix("/.default")}
    if client_id:
        query["client_id"] = client_id
    endpoint, header = os.environ.get("IDENTITY_ENDPOINT"), os.environ.get("IDENTITY_HEADER")
    if endpoint and header:  # a Function App or App Service
        address = f"{endpoint}?api-version=2019-08-01&{urllib.parse.urlencode(query)}"
        headers, wait = {"X-IDENTITY-HEADER": header}, 30
    else:  # a virtual machine: its metadata service
        address = "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&"
        address += urllib.parse.urlencode(query)
        headers, wait = {"Metadata": "true"}, 2
    answer = ask(address, None, headers, "The managed identity's sign-in", wait, direct=True)
    return answer["access_token"], float(answer.get("expires_on") or time.time() + 3600)
'''

_APP = '''
# Sign in as an app registration (service principal), added to the environment as an application
# user. Its client secret is a key vault's secret, read by name: never typed here.
tenant_id = "my-tenant-id"
client_id = "my-client-id"
client_secret = secret("client secret")


def sign_in(scope):
    """Microsoft's client credentials request: the token, and when it runs out."""
    login = os.environ.get("DATAVERSE_LOGIN_URL", "https://login.microsoftonline.com")
    form = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scope,
    }
    sent = urllib.parse.urlencode(form).encode()
    answer = ask(f"{login}/{tenant_id}/oauth2/v2.0/token", sent, {}, "The sign-in")
    return answer["access_token"], time.time() + int(answer.get("expires_in", 3600))
'''

_CONNECTION = r'''

class DataverseError(RuntimeError):
    """The sign-in or Dataverse refused. The message is its own words, and what usually causes it."""


def ask(address, data, headers, what, wait=120, direct=False):
    """One web request (with `data`, a POST; without, a GET): its JSON answer. `direct`: a local
    endpoint (the managed identity's), reached without a proxy."""
    request = urllib.request.Request(address, data, headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if direct else None
    try:
        with (opener.open if opener else urllib.request.urlopen)(request, timeout=wait) as answer:
            return json.loads(answer.read() or b"{}")
    except urllib.error.HTTPError as refused:
        raise DataverseError(why(what, refused.code, refused.read())) from None
    except (urllib.error.URLError, TimeoutError) as error:
        host = urllib.parse.urlsplit(address).netloc
        reason = getattr(error, "reason", error)
        more = " A managed identity signs in only inside Azure." if direct else ""
        raise DataverseError(f"{what} could not reach {host}: {reason}.{more}") from None


def why(what, status, body):
    """A refusal in plain words: the service's own message, then what usually causes that status."""
    try:
        said = json.loads(body)
        error = said.get("error_description") or said.get("error") or said
    except (ValueError, AttributeError):
        error = body.decode("utf-8", "replace")[:300]
    if isinstance(error, dict):
        error = error.get("message") or error.get("code") or "no reason"
    hints = {
        401: "Check the sign-in: an app registration's tenant id, client id and client secret, or that "
        "you are signed in (az login).",
        403: "The sign-in reached Dataverse, but its user may not read this: an admin adds the app "
        "registration or managed identity as an application user, with a security role that reads it.",
        404: "Check the environment's address and the table's name.",
        429: "Dataverse limits how many requests one sign-in makes: wait a minute.",
    }
    first = str(error).strip().splitlines()[0] if str(error).strip() else "no reason"
    return f"{what} was refused ({status}): {first} {hints.get(status, '')}".strip()


def label_of(label):
    """A metadata Label's words: the user's own language's, else the first one given."""
    if not isinstance(label, dict):
        return ""
    own = label.get("UserLocalizedLabel") or {}
    if own.get("Label"):
        return str(own["Label"])
    for each in label.get("LocalizedLabels") or []:
        if each.get("Label"):
            return str(each["Label"])
    return ""


def kind_of(attribute):
    """A column's type in Dataverse's words: String, Money, Lookup, Picklist, MultiSelectPicklist..."""
    named = str((attribute.get("AttributeTypeName") or {}).get("Value") or "")
    if named in ("MultiSelectPicklistType", "FileType", "ImageType"):
        return named.removesuffix("Type")
    return str(attribute.get("AttributeType") or named.removesuffix("Type"))


def columns_of(attributes):
    """The columns a read gives, sorted by name: {"name", "type", "title" (the display name), "field"
    (what the Web API calls it: a lookup's id is _name_value), "label" (read as its formatted value: a
    choice column's label, a lookup's name)}. A lookup's `name` + "name" column (the SQL endpoint has
    it too) is the lookup's label; other parts of columns, files and images are not read."""
    by_name = {str(a.get("LogicalName") or ""): a for a in attributes}
    out = []
    for name, a in sorted(by_name.items()):
        kind = kind_of(a)
        if not name or a.get("IsValidForRead") is False:
            continue
        title = label_of(a.get("DisplayName"))
        parent = a.get("AttributeOf")
        if parent:
            owner = by_name.get(str(parent))
            if owner is not None and kind_of(owner) in Dataverse.LOOKUPS and name == f"{parent}name":
                out.append({"name": name, "type": "String", "title": title, "field": f"_{parent}_value",
                            "label": True})  # fmt: skip
            continue
        if kind in Dataverse.UNREAD:
            continue
        field = f"_{name}_value" if kind in Dataverse.LOOKUPS else name
        out.append({"name": name, "type": kind, "title": title, "field": field,
                    "label": kind in Dataverse.CHOICES})  # fmt: skip
    return out


def when(value):
    """A date the Web API wrote as text (2026-01-31T09:30:00Z), as a date."""
    if not isinstance(value, str):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value


def row_of(record, columns):
    """One record of the Web API's answer as a row: each column under its own name, a choice column as
    its label, a lookup as its id (and its name column as its label), a date as a date."""
    row = {}
    for c in columns:
        value = record.get(c["field"])
        if c["label"]:
            value = record.get(c["field"] + Dataverse.LABEL, value if c["type"] != "String" else None)
        row[c["name"]] = when(value) if c["type"] == "DateTime" else value
    return row


def query_of(entity_set, fields=(), filter=None, order_by=None, top=None, count=False):
    """A table's read as OData: its entity set, then $select, $filter, $orderby, $top and $count."""
    asked = []
    if fields:
        asked.append(("$select", ",".join(fields)))
    if filter:
        asked.append(("$filter", str(filter)))
    if order_by:
        asked.append(("$orderby", str(order_by)))
    if top is not None:
        asked.append(("$top", str(int(top))))
    if count:
        asked.append(("$count", "true"))
    words = "&".join(f"{k}={urllib.parse.quote(v, safe=Dataverse.SAFE)}" for k, v in asked)
    return entity_set + (f"?{words}" if words else "")


def frame_of(rows, names):
    """Rows as a pandas DataFrame when pandas is here, else as they are (a list of dicts)."""
    try:
        import pandas as pd
    except ImportError:
        return rows
    return pd.DataFrame.from_records(rows, columns=names)


def sql_connection_string(address):
    """The SQL endpoint's ODBC connection string: the environment's host, port 5558, encrypted. No user
    and no password in it: the token goes beside it (SQL_COPT_SS_ACCESS_TOKEN)."""
    host = urllib.parse.urlsplit(address).hostname
    return (
        "Driver={ODBC Driver 18 for SQL Server};"
        + f"Server={host},{Dataverse.SQL_PORT};"
        + "Encrypt=yes;"
        + "TrustServerCertificate=no;"
    )


def token_struct(token):
    """An access token as the ODBC driver takes it: its length, then the token in UTF-16-LE."""
    sent = token.encode("utf-16-le")
    return struct.pack(f"<I{len(sent)}s", len(sent), sent)


def sql_words(error):
    """A refusal from the SQL endpoint in plain words."""
    said = str(error)
    if re.search(r"TDS.{0,80}(disabled|not enabled|turned off)|endpoint.{0,20}disabled", said, re.I | re.S):
        return Dataverse.TDS_OFF
    if re.search(r"IM002|Can't open lib|Data source name not found", said):
        return "Dataverse's SQL endpoint needs Microsoft's ODBC Driver 18 for SQL Server on this computer."
    first = said.strip().splitlines()[0] if said.strip() else type(error).__name__
    return f"Dataverse's SQL endpoint refused: {first[:400]}"


class SqlCursor:
    """A cursor on the SQL endpoint whose refusals are said in plain words."""

    def __init__(self, inner):
        self.inner = inner

    @property
    def description(self):
        return self.inner.description

    @property
    def rowcount(self):
        return self.inner.rowcount

    def execute(self, sql, *parameters):
        try:
            self.inner.execute(sql, *parameters)
        except Exception as error:  # the driver's own error class
            raise DataverseError(sql_words(error)) from None
        return self

    def fetchall(self):
        return self.inner.fetchall()

    def fetchmany(self, size=1):
        return self.inner.fetchmany(size)

    def fetchone(self):
        return self.inner.fetchone()

    def close(self):
        self.inner.close()


class Dataverse:
    """A Dataverse environment: its tables read through the Web API, SQL on its read-only SQL endpoint.

        conn.tables()                     each table: its logical name, display name and entity set
        conn.columns("account")           a table's columns: name, type, display name
        conn.read("account")              its rows (a DataFrame), each choice column as its labels
        conn.read("account", columns=["name", "revenue"], filter="revenue gt 100000", limit=50)
        conn.fetch("<fetch>...</fetch>")  a FetchXML query's rows
        conn.cursor()                     SQL (SELECT only) on the SQL endpoint, port 5558: pyodbc and
                                          Microsoft's ODBC Driver 18, signed in with the same token
        conn.url, conn.access_token()     for any other Web API request (conn.api is its root)
    """

    API = "/api/data/v9.2"
    LABEL = "@OData.Community.Display.V1.FormattedValue"
    LABELS = 'odata.include-annotations="OData.Community.Display.V1.FormattedValue"'
    CHOICES = frozenset({"Picklist", "State", "Status", "MultiSelectPicklist"})  # a Yes/No stays true/false
    LOOKUPS = frozenset({"Lookup", "Customer", "Owner"})
    # Never read as a value: the parts of other columns, files, images, calendars, party lists.
    UNREAD = frozenset({"Virtual", "EntityName", "ManagedProperty", "PartyList", "CalendarRules",
                        "File", "Image"})  # fmt: skip
    PAGE = 5000  # the most rows Dataverse gives in one answer
    SAFE = ",'()/:@"
    SQL_PORT = 5558
    TABLE_FIELDS = "LogicalName,EntitySetName,DisplayName,PrimaryIdAttribute,PrimaryNameAttribute"
    COLUMN_FIELDS = "LogicalName,AttributeType,AttributeTypeName,DisplayName,AttributeOf,IsValidForRead"
    TDS_OFF = (
        "Dataverse's SQL endpoint (TDS) is off in this environment. The environment's administrator "
        "turns on \"Enable TDS endpoint\" in the Power Platform admin center (the environment's "
        "Settings, then Product, then Features)."
    )

    def __init__(self, address, sign_in):
        parts = urllib.parse.urlsplit(str(address).strip())
        local = parts.hostname in ("127.0.0.1", "localhost")
        if not parts.hostname or not (parts.scheme == "https" or (parts.scheme == "http" and local)):
            raise DataverseError(
                f"The environment's address is https://<name>.crm.dynamics.com (Power Apps: Settings, "
                f"Session details), not {address!r}."
            )
        self.url = f"{parts.scheme}://{parts.netloc}"
        self.api = self.url + self.API
        self.scope = self.url + "/.default"
        self.sign_in, self.token, self.expires = sign_in, "", 0.0
        self.found, self.known, self.sql = None, {}, None
        self.get("WhoAmI", "Signing in to Dataverse")  # signs in and reaches it now: Test means it

    # ===== the Web API =====

    def access_token(self):
        """The token, signed in again when it has five minutes or less to run."""
        if time.time() > self.expires - 300:
            self.token, self.expires = self.sign_in(self.scope)
        return self.token

    def get(self, path, what, prefer=None):
        """One GET on the Web API (a path under its root, or a next page's whole address): its JSON."""
        if "://" in path and not path.startswith(self.api + "/"):
            raise DataverseError(f"{what}: Dataverse sent an address outside {self.url}; it is not followed.")
        headers = {
            "Authorization": f"Bearer {self.access_token()}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        }
        if prefer:
            headers["Prefer"] = prefer
        return ask(path if "://" in path else f"{self.api}/{path}", None, headers, what)

    def tables(self):
        """Each table this sign-in may see: {"table" (its logical name), "title" (its display name),
        "set" (its entity set, the Web API's name for it)}. Read once."""
        if self.found is None:
            path = f"EntityDefinitions?$select={self.TABLE_FIELDS}&$filter=IsPrivate%20eq%20false"
            listed = self.get(path, "Listing the tables").get("value") or []
            self.found = [self.listed(t) for t in listed if t.get("LogicalName") and t.get("EntitySetName")]
            self.found.sort(key=lambda t: t["table"])
        return [dict(t) for t in self.found]

    @staticmethod
    def listed(table):
        return {
            "table": str(table["LogicalName"]),
            "title": label_of(table.get("DisplayName")),
            "set": str(table["EntitySetName"]),
        }

    def table(self, name):
        """One table, by its logical name, its entity set or its display name (any case)."""
        wanted = str(name).strip().casefold()
        found = self.tables()
        for key in ("table", "set", "title"):
            for t in found:
                if t[key].casefold() == wanted:
                    return t
        some = ", ".join(t["table"] for t in found[:12]) + (" ..." if len(found) > 12 else "")
        raise DataverseError(
            f"Dataverse has no table {str(name)!r} this sign-in may read. It has: {some or 'none'}."
        )

    def described(self, name):
        """A table's columns as a read gives them (columns_of), read once."""
        logical = self.table(name)["table"]
        if logical not in self.known:
            if not re.fullmatch(r"[a-z0-9_]+", logical):
                raise DataverseError(f"{logical!r} is not a table's logical name.")
            path = f"EntityDefinitions(LogicalName='{logical}')/Attributes?$select={self.COLUMN_FIELDS}"
            found = self.get(path, f"Reading {logical}'s columns").get("value") or []
            self.known[logical] = columns_of(found)
        return self.known[logical]

    def columns(self, name):
        """A table's columns: {"column", "type", "title"}."""
        return [{"column": c["name"], "type": c["type"], "title": c["title"]} for c in self.described(name)]

    def catalog(self):
        """Every table's columns as a catalog, one row each, in one schema (dbo, as the SQL endpoint
        names its tables); each table's display name is a row with no column."""
        path = (
            f"EntityDefinitions?$select={self.TABLE_FIELDS}&$filter=IsPrivate%20eq%20false"
            f"&$expand=Attributes($select={self.COLUMN_FIELDS})"
        )
        listed = self.get(path, "Reading the tables' columns").get("value") or []
        rows, found = [], []
        for t in sorted(listed, key=lambda t: str(t.get("LogicalName") or "")):
            if not t.get("LogicalName") or not t.get("EntitySetName"):
                continue
            table = self.listed(t)
            found.append(table)
            columns = columns_of(t.get("Attributes") or [])
            self.known[table["table"]] = columns
            place = {"table_schema": "dbo", "table_name": table["table"]}
            rows.append(place | {"column_name": "", "data_type": "", "description": table["title"]})
            rows += [
                place | {"column_name": c["name"], "data_type": c["type"], "description": c["title"]}
                for c in columns
            ]
        self.found = found
        if not found:
            raise DataverseError("Dataverse listed no tables this sign-in may read.")
        return rows

    def pages(self, path, limit):
        """A read's records, page after page (@odata.nextLink) until `limit` (None: every one), and
        what it said of the count: (records, count, more than 5,000)."""
        size = self.PAGE if limit is None else max(1, min(self.PAGE, int(limit)))
        prefer = f"{self.LABELS},odata.maxpagesize={size}"
        records, count, more, at = [], None, False, path
        while at:
            answer = self.get(at, "Reading the table", prefer)
            if at is path:
                count = answer.get("@odata.count")
                more = bool(answer.get("@Microsoft.Dynamics.CRM.totalrecordcountlimitexceeded"))
            records += answer.get("value") or []
            if limit is not None and len(records) >= limit:
                return records[:limit], count, more
            at = answer.get("@odata.nextLink")
        return records, count, more

    def count(self, name):
        """How many rows a table holds, by Dataverse's own count (a snapshot, refreshed daily); None
        when it does not say."""
        logical = self.table(name)["table"]
        asked = urllib.parse.quote(json.dumps([logical]), safe="")
        try:
            said = self.get(f"RetrieveTotalRecordCount(EntityNames=@p)?@p={asked}", "Counting the rows")
            values = (said.get("EntityRecordCountCollection") or {}).get("Values") or []
            return int(values[0]) if values else None
        except (DataverseError, TypeError, ValueError):
            return None

    def rows(self, name, columns=None, filter=None, order_by=None, limit=None, frame=False):
        """A table's rows and how many it holds (None: not known): `columns` (its columns' names; none:
        every one), an OData `filter` ("revenue gt 100000") and `order_by` ("name desc"), the first
        `limit` rows (None: every row). `frame`: the rows as a DataFrame."""
        table = self.table(name)
        known = self.described(table["table"])
        picked = known
        if columns:
            by_name = {c["name"].casefold(): c for c in known}
            missing = [c for c in columns if str(c).casefold() not in by_name]
            if missing:
                raise DataverseError(f"{table['table']} has no column {missing[0]!r}.")
            picked = [by_name[str(c).casefold()] for c in columns]
        fields = list(dict.fromkeys(c["field"] for c in picked))
        one_page = limit is not None and int(limit) <= self.PAGE
        path = query_of(table["set"], fields, filter, order_by, int(limit) if one_page else None, True)
        records, count, more = self.pages(path, limit)
        total = None
        if isinstance(count, int) and not more:
            total = count
        elif more and not filter:
            total = self.count(table["table"])
        found = [row_of(r, picked) for r in records]
        return (frame_of(found, [c["name"] for c in picked]) if frame else found), total

    def read(self, name, columns=None, filter=None, order_by=None, limit=None):
        """A table's rows as a DataFrame (a list of dicts without pandas): rows() without the count."""
        return self.rows(name, columns, filter, order_by, limit, frame=True)[0]

    def fetch(self, fetch_xml):
        """A FetchXML query's rows (its first page: at most 5,000, or its `count`), as a DataFrame:
        choice columns as their labels, lookups as their ids; aliased columns as they come."""
        entity = re.search(r"<entity\b[^>]*\bname\s*=\s*[\"']([A-Za-z0-9_]+)[\"']", str(fetch_xml))
        if entity is None:
            raise DataverseError('A FetchXML query names its table: <entity name="account">.')
        table = self.table(entity.group(1))
        known = self.described(table["table"])
        path = f"{table['set']}?fetchXml={urllib.parse.quote(str(fetch_xml), safe='')}"
        records = self.get(path, "The FetchXML query", self.LABELS).get("value") or []
        present = {key for r in records for key in r}
        used = [c for c in known if c["field"] in present]
        taken = {c["field"] for c in used}
        extra = [k for k in dict.fromkeys(k for r in records for k in r) if "@" not in k and k not in taken]
        found = [row_of(r, used) | {k: r.get(k) for k in extra} for r in records]
        return frame_of(found, [c["name"] for c in used] + extra)

    def tested(self, rows=20):
        """Test: it signed in (above); how many tables it sees, and the first rows of one."""
        listed = self.tables()
        found = {"found": f"signed in and found {len(listed)} table{'' if len(listed) == 1 else 's'}"}
        first = next((t for t in listed if t["table"] == "account"), listed[0] if listed else None)
        if first is not None:
            got, total = self.rows(first["table"], limit=rows)
            found["preview"] = {"table": first["table"], "rows": got, "total": total}
        return found

    # ===== SQL, on the read-only SQL endpoint =====

    def cursor(self):
        """A cursor on the SQL endpoint (T-SQL, SELECT only), connected on first use."""
        if self.sql is None:
            import pyodbc

            attrs = {1256: token_struct(self.access_token())}  # 1256: SQL_COPT_SS_ACCESS_TOKEN
            try:
                self.sql = pyodbc.connect(sql_connection_string(self.url), attrs_before=attrs)
            except Exception as error:  # the driver's own error class
                raise DataverseError(sql_words(error)) from None
        return SqlCursor(self.sql.cursor())

    def close(self):
        if self.sql is not None:
            self.sql.close()
            self.sql = None


conn = Dataverse(url, sign_in)'''


def _code(sign_in: str, imports: str = "") -> str:
    return _IMPORTS + imports + _WHERE + sign_in + _CONNECTION


YOU: str = _code(_YOU, "\nfrom azure.identity import DefaultAzureCredential\n")
MANAGED: str = _code(_MANAGED)
APP: str = _code(_APP)

# The form's Sign in: (label, a text only that way's code holds, its code). As you comes first.
SIGN_INS: tuple[tuple[str, str, str], ...] = (
    ("As you (Azure command line or browser)", "DefaultAzureCredential", YOU),
    ("Managed identity (in Azure: a Function App, App Service or VM)", "IDENTITY_HEADER", MANAGED),
    ("App registration, its secret from a key vault", 'client_secret = secret("client secret")', APP),
)
