"""SQL Server and Azure SQL as connections, made robust (the owner, 2026-11-17: "SQL server and azure SQL
are two things I use alot so make them robust").

The connection is a starter (server/blade_templates.py DATABASES: sqlserver, azuresql), modelled on the
Dataverse and Power BI ones: its code signs in and makes `conn`, a `SqlServer` object written here as
text (RUNTIME, standard library only; Microsoft's mssql-python and, for two sign-ins, azure-identity are
imported where they are used), so the same code runs in the app's child process, a Workbench kernel, an
exported script, an Azure Function App and a hosted Streamlit app as it is (the owner, 2026-11-17: "odbc
does not work on function apps" / "We need both Python-TDS for Dataverse and mssql for azure and sql server
connections"). `conn` is shaped like the driver's connection (cursor, commit, rollback, close; anything
else is the driver's own), so the catalog, Open as grid, SQL cells and the Write starters use it as they
use mssql-python. What it adds:

  driver      Microsoft's mssql-python only: a pip package that carries its own driver, so nothing else is
              installed (no ODBC driver, no driver manager); missing, the pip command in plain words.
              `conn.about()` says it (the card)
  sign-ins    SQL login; Windows (Trusted_Connection: Kerberos; this machine's only); Microsoft Entra: as
              you (Azure command line, Visual Studio Code, else a browser window: azure-identity; this
              machine's only), a managed identity (system, or a user-assigned client id), an app
              registration with a client secret (a vault's, never typed) or a certificate, an Entra
              password, the driver's Entra default (ActiveDirectoryDefault: a managed identity in Azure).
              A token goes beside the connection string (SQL_COPT_SS_ACCESS_TOKEN, TOKEN_CODE: the one code
              for it, OneLake's SQL endpoint uses it too) and is taken again five minutes before it runs
              out (a new connection)
  options     Encrypt (mandatory, optional, strict), Trust server certificate, Host name in certificate,
              port or a named instance (server\\instance), read-only intent (ApplicationIntent=ReadOnly: a
              read replica) for reads, the Write starters' connection without it (`for_writes()`),
              MultiSubnetFailover, the login and query timeouts
  errors      SQL Server's errors in plain words with the fix (ERRORS, said by `explain`): mssql-python
              gives the server's words without its number, so each is known by its number (where a text
              holds one) or its words (WORDS): a login refused (18456), the Azure firewall (40615, with
              the address it named), a paused serverless database (40613), an untrusted certificate, a
              missing mssql-python, a server not found, a timeout
  retries     Azure's passing errors (TRANSIENT, by number or words) on connect and on a read, again after
              1, 2, 4... seconds (at most 16 apart); a paused serverless database is waited for up to
              RESUME_SECONDS, said as it goes ("resuming"). A write is never retried here: the Write starters
              run the whole transaction again (client/write_sql.py)
  reads       `conn.read_arrow(sql)`: mssql-python's own Arrow batches where it reads every column, else
              fetched in batches into Arrow; either way each column typed as `arrow_type` says
              (decimal(p,s) exact, money as decimal(19,4), tinyint unsigned, datetimeoffset kept as an
              instant, TIMESTAMPTZ); geography, geometry, hierarchyid and sql_variant read as text (a plain
              read of a table: .ToString() and CAST, sys.columns asked once per table)
  cancel      a statement runs while the caller waits; an interrupt (the kernel's Interrupt, Ctrl+C)
              sends SQLCancel (mssql-python's statement handle) and stops it on the server

The rest of this module is the T-SQL the app sends (the catalog from the system views, the foreign keys
for the ERD, a table's row count from sys.partitions) and the rules for what comes back. Pure: no I/O.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from swissarmybench.domain import entra
from swissarmybench.domain.catalogs import quote_identifier

if TYPE_CHECKING:  # the model is imported where it is built: the plain client imports this module
    from swissarmybench.domain.relationships import Model

DIALECT = "sqlserver"
TEMPLATES: frozenset[str] = frozenset({"sqlserver", "azuresql"})

# ===== the errors, in plain words =====
#
# Each entry: the number SQL Server (or the SQLSTATE the driver) gives, what it means, and the fix. The
# connection's code holds this table (RUNTIME, as JSON) and `explain` below reads it the same way.

ERRORS: dict[str, tuple[str, str]] = {
    "18456": (
        "The server refused the sign-in (login failed).",
        "Check the user name and password, or that this sign-in has a login on the server and a user in "
        "the database. The server's error log names the reason (its state: 5 an unknown user, 8 a wrong "
        "password, 38 a database it may not open, 58 a server that takes Windows sign-ins only).",
    ),
    "18452": (
        "The server does not trust this Windows sign-in (it is from another domain).",
        "Sign in with a SQL login or Microsoft Entra, or from a computer in the server's domain.",
    ),
    "18470": ("The login is disabled.", "Ask the server's administrator to enable it."),
    "18488": ("The password has expired.", "Change it, then sign in again."),
    "4060": (
        "The server cannot open the database this sign-in asked for.",
        "Check the database's name, and that this sign-in has a user in it.",
    ),
    "40532": (
        "Azure SQL cannot open the server the sign-in named.",
        "Check the server's name (my-server.database.windows.net) and the user name.",
    ),
    "40615": (
        "Azure SQL's firewall refused this computer{address}.",
        "Add the address in the Azure portal: the server's Networking page, Firewall rules (or Add your "
        "client IPv4 address); or reach the server through a private endpoint.",
    ),
    "40613": (
        "The database is not available yet: a serverless database that was paused is resuming, or the "
        "database is being moved.",
        "Wait a minute and try again (the connection waits for it by itself first).",
    ),
    "40197": ("Azure SQL was busy moving the database.", "Try again: it passes by itself."),
    "40501": ("Azure SQL is busy.", "Try again in a few seconds."),
    "49918": ("Azure SQL has too many requests in progress.", "Try again in a few seconds."),
    "49919": ("Azure SQL has too many requests for this subscription.", "Try again in a few seconds."),
    "49920": ("Azure SQL has too many operations in progress.", "Try again in a few seconds."),
    "10928": ("The database reached its limit of sessions or workers.", "Try again, or scale it up."),
    "10929": ("The database is too busy for this request now.", "Try again in a few seconds."),
    "4221": ("A read replica is catching up.", "Try again in a few seconds."),
    "229": (
        "This sign-in may not read that object.",
        "Ask for SELECT on it (or the db_datareader role) in this database.",
    ),
    "208": ("The server has no table or view by that name here.", "Check the schema and the name."),
    "207": ("The table has no column by that name.", "Check the column's name."),
    "1205": ("The statement was chosen as a deadlock's victim.", "Run it again."),
    "3906": (
        "The database is read-only here: the connection asked for a read replica (Read-only intent).",
        "Untick Read-only intent for this connection, or write with a Write starter (it asks for the "
        "primary).",
    ),
    "33155": (
        "Microsoft Entra refused the sign-in for this database.",
        "Add the identity as a user: CREATE USER [name] FROM EXTERNAL PROVIDER.",
    ),
    "certificate": (
        "The server's certificate is not one this computer trusts (mssql-python encrypts by default).",
        "Tick Trust server certificate (a server with a self-signed certificate, on your own network), "
        "or install the server's certificate authority on this computer.",
    ),
    "driver": (
        "SQL Server needs Microsoft's mssql-python in this Python (it carries its own driver: nothing else "
        "to install).",
        "Install it: pip install mssql-python.",
    ),
    "not found": (
        "The server could not be reached: no server by that name answered.",
        "Check the server's name and port (or the instance: server\\instance, with SQL Server Browser "
        "running), that it takes TCP connections, and the network (a VPN).",
    ),
    "HYT00": (
        "The server did not answer in time.",
        "Check the server's name and the network; raise the login timeout for a slow link.",
    ),
    "mfa": (
        "The account needs multi-factor sign-in (AADSTS50076, or AADSTS50079 to set it up): a user name and "
        "password sign-in cannot do MFA.",
        "Pick the sign-in '" + entra.MFA_LABEL + "' instead, or an app registration.",
    ),
    "kerberos": (
        "Windows sign-in found no Kerberos ticket on this computer.",
        "Run kinit user@REALM first (Linux, macOS), or sign in another way.",
    ),
}
# mssql-python says the server's words without its number: each known number by its words (lower case,
# the first that a message holds wins, so the longer phrase comes first).
WORDS: tuple[tuple[str, str], ...] = (
    ("aadsts50076", "mfa"),  # Entra's own codes first: its message also says the login failed
    ("aadsts50079", "mfa"),
    ("is not allowed to access the server", "40615"),
    ("not currently available", "40613"),
    ("the service has encountered an error processing your request", "40197"),
    ("the service is currently busy", "40501"),
    ("not enough resources to process request", "49918"),
    ("too many create or update operations in progress", "49919"),
    ("too many operations in progress for subscription", "49920"),
    ("the server is currently too busy", "10929"),
    ("limit for the database is", "10928"),
    ("login to read-secondary failed", "4221"),
    ("login is from an untrusted domain", "18452"),
    ("the account is disabled", "18470"),
    ("password of the account has expired", "18488"),
    ("password of the account must be changed", "18488"),
    ("cannot open database", "4060"),
    ("cannot open server", "40532"),
    ("login failed", "18456"),
    ("permission was denied on the object", "229"),
    ("invalid object name", "208"),
    ("invalid column name", "207"),
    ("deadlocked on lock", "1205"),
    ("because the database is read-only", "3906"),
    ("no module named 'mssql_python'", "driver"),
)
# A dropped connection, as the driver says it: its socket error's code (hex) or its words.
DROPPED: tuple[str, ...] = (
    "error code 0x2745",  # 10053
    "error code 0x2746",  # 10054
    "error code 0x274c",  # 10060
    "communication link failure",
)
# The server not found: name resolution's codes (11001, 11002) and words.
NOT_FOUND: tuple[str, ...] = (
    "could not open a connection",
    "server was not found",
    "server is not found",
    "name or service not known",
    "no such host",
    "(11001)",
    "error code 0x2af9",
    "error code 0x2afa",
)
# Numbers whose error passes by itself (Azure's documented transient errors, a dropped connection).
TRANSIENT: frozenset[str] = frozenset(
    {"40613", "40197", "40501", "49918", "49919", "49920", "4221", "10928", "10929"}
    | {"10053", "10054", "10060", "233", "64"}
)
TRANSIENT_STATES: frozenset[str] = frozenset({"08S01", "08S02"})
RESUME_SECONDS: int = 60  # how long a paused serverless database is waited for
TRIES: int = 5  # a connect or a read, at most this many times for any other passing error

_NUMBER = re.compile(r"\((\d{2,5})\)")
_STATE = re.compile(r"^\[?([0-9A-Z]{5})\]?")


def error_key(message: str) -> str | None:
    """Which entry of ERRORS an error's text is: its number first, then its words, then its SQLSTATE."""
    text = message or ""
    for number in _NUMBER.findall(text):
        if number in ERRORS:
            return str(number)
    lowered = text.lower()
    if "certificate" in lowered and ("not trusted" in lowered or "verify failed" in lowered):
        return "certificate"
    if "kerberos" in lowered or ("gss" in lowered and "credential" in lowered):
        return "kerberos"
    if any(words in lowered for words in NOT_FOUND):
        return "not found"
    for words, key in WORDS:
        if words in lowered:
            return key
    found = _STATE.match(text.strip())
    if found and found.group(1) in ERRORS:
        return str(found.group(1))
    if "login timeout" in lowered or "timeout expired" in lowered:
        return "HYT00"
    return None


def explain(message: str) -> str:
    """An error's text in plain words with its fix (the driver's own text after it), or the text as it
    is when ERRORS has nothing for it."""
    key = error_key(message)
    if key is None:
        return message
    words, fix = ERRORS[key]
    address = re.search(r"IP address '([^']+)'", message or "")
    named = f" (its address, {address.group(1)}, is not allowed)" if address else ""
    return f"{words.replace('{address}', named)} {fix}"


def transient(message: str) -> bool:
    """Whether an error passes by itself (try again), by its numbers, its words and its SQLSTATE."""
    text = message or ""
    found = _STATE.match(text.strip())
    if found and found.group(1) in TRANSIENT_STATES:
        return True
    if set(_NUMBER.findall(text)) & TRANSIENT:
        return True
    lowered = text.lower()
    if any(words in lowered for words in DROPPED):
        return True
    return any(words in lowered and key in TRANSIENT for words, key in WORDS)


# ===== the connection's code: the runtime, then each way to sign in =====

# The one code for an Entra token beside a connection string (mssql-python; OneLake's SQL endpoint too).
TOKEN_CODE: str = '''
def token_struct(token):
    """An access token as the driver takes it: its length, then the token in UTF-16-LE."""
    sent = token.encode("utf-16-le")
    return struct.pack(f"<I{len(sent)}s", len(sent), sent)
'''  # noqa: S105 (code, not a password)

_IMPORTS = """import importlib
import json
import os
import re
import struct
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
"""

RUNTIME: str = (
    TOKEN_CODE
    + r'''

class SqlServerError(RuntimeError):
    """SQL Server, Azure SQL or the driver refused: what it means and the fix, then the driver's words."""


ERRORS = json.loads(ERRORS_JSON)
WORDS = json.loads(WORDS_JSON)
DROPPED = json.loads(DROPPED_JSON)
NOT_FOUND = json.loads(NOT_FOUND_JSON)
TRANSIENT = set(TRANSIENT_JSON)
TRANSIENT_STATES = {"08S01", "08S02"}
_NUMBER = re.compile(r"\((\d{2,5})\)")
_STATE = re.compile(r"^\[?([0-9A-Z]{5})\]?")
_UDT = {"geography", "geometry", "hierarchyid"}
_PLAIN_READ = re.compile(
    r"^\s*SELECT\s+(?P<top>TOP\s*\(?\s*\d+\s*\)?\s+)?(?P<columns>\*|\[(?:[^\]]|\]\])+\](?:\s*,\s*\[(?:[^\]]|\]\])+\])*)"
    r"\s+FROM\s+(?P<object>(?:\[(?:[^\]]|\]\])+\]\.){0,2}\[(?:[^\]]|\]\])+\])(?P<rest>\s+WHERE\s.*)?\s*;?\s*$",
    re.IGNORECASE | re.DOTALL,
)


def error_key(message):
    """Which entry of ERRORS an error's text is: its number, its words, then its SQLSTATE."""
    text = message or ""
    for number in _NUMBER.findall(text):
        if number in ERRORS:
            return number
    lowered = text.lower()
    if "certificate" in lowered and ("not trusted" in lowered or "verify failed" in lowered):
        return "certificate"
    if "kerberos" in lowered or ("gss" in lowered and "credential" in lowered):
        return "kerberos"
    if any(words in lowered for words in NOT_FOUND):
        return "not found"
    for words, key in WORDS:
        if words in lowered:
            return key
    found = _STATE.match(text.strip())
    if found and found.group(1) in ERRORS:
        return found.group(1)
    if "login timeout" in lowered or "timeout expired" in lowered:
        return "HYT00"
    return None


def explain(message):
    """The error in plain words with its fix, or as it is."""
    key = error_key(message)
    if key is None:
        return message
    words, fix = ERRORS[key]
    address = re.search(r"IP address '([^']+)'", message or "")
    named = f" (its address, {address.group(1)}, is not allowed)" if address else ""
    return f"{words.replace('{address}', named)} {fix}"


def said(error):
    """A driver error's own words: mssql-python's ("Driver Error: ...; DDBC Error: ..."), else its text."""
    args = [str(a) for a in getattr(error, "args", ())]
    return " ".join(args) if args else str(error)


def passing(error):
    """Whether an error passes by itself: Azure's transient numbers or words, a dropped connection."""
    args = [str(a) for a in getattr(error, "args", ())]
    if args and args[0] in TRANSIENT_STATES:
        return True
    text = said(error)
    if set(_NUMBER.findall(text)) & TRANSIENT:
        return True
    lowered = text.lower()
    if any(words in lowered for words in DROPPED):
        return True
    return any(words in lowered and key in TRANSIENT for words, key in WORDS)


def resuming(error):
    return error_key(said(error)) == "40613"


def braced(value):
    """A value as a connection string holds it: in braces when it has ; or a brace (} doubled)."""
    text = str(value)
    if re.search(r"[;{}=\s]", text) or text != text.strip():
        return "{" + text.replace("}", "}}") + "}"
    return text


def password(value):
    """PWD= with the password always in braces (a } in it doubled)."""
    return "PWD={" + str(value or "").replace("}", "}}") + "}"


def arrow_type(pa, kind, size, precision, scale, values):
    """A column's Arrow type: from the driver's description (its Python type, size, precision and
    scale), and its values where the description cannot tell (a time zone)."""
    import datetime as dt
    import decimal
    import uuid

    if kind is bool:
        return pa.bool_()
    if kind is int:
        return {3: pa.uint8(), 5: pa.int16(), 10: pa.int32()}.get(precision or 0, pa.int64())
    if kind is float:
        return pa.float32() if (precision or 53) <= 24 else pa.float64()
    if kind is decimal.Decimal:
        p = int(precision or 38)
        return pa.decimal128(min(max(p, 1), 38), max(0, min(int(scale or 0), p)))
    if kind is dt.datetime or kind is dt.datetime.__name__:
        zoned = any(getattr(v, "tzinfo", None) is not None for v in values if v is not None)
        return pa.timestamp("us", tz="UTC") if zoned else pa.timestamp("us")
    if kind is dt.date:
        return pa.date32()
    if kind is dt.time:
        return pa.time64("us")
    if kind in (bytes, bytearray, memoryview):
        return pa.binary()
    if kind is uuid.UUID:
        return pa.string()
    if any(getattr(v, "tzinfo", None) is not None for v in values if isinstance(v, dt.datetime)):
        return pa.timestamp("us", tz="UTC")  # a datetimeoffset the driver described as text
    return pa.string()


def arrow_typed(pa, table):
    """mssql-python's Arrow table with the same types the rows' path makes: an instant in UTC, a time in
    microseconds, plain strings and bytes (not large ones)."""
    fields = []
    for field in table.schema:
        kind = field.type
        if pa.types.is_timestamp(kind):
            kind = pa.timestamp("us", tz="UTC" if kind.tz else None)
        elif pa.types.is_time(kind):
            kind = pa.time64("us")
        elif pa.types.is_large_string(kind):
            kind = pa.string()
        elif pa.types.is_large_binary(kind):
            kind = pa.binary()
        fields.append(pa.field(field.name, kind, True))
    return table.cast(pa.schema(fields))


def arrow_values(values, kind):
    """The values as Arrow takes them for their type: an id as its text, a zoned time in UTC."""
    import datetime as dt
    import uuid

    out = []
    for v in values:
        if isinstance(v, uuid.UUID):
            v = str(v)
        elif isinstance(v, dt.datetime) and v.tzinfo is not None:
            v = v.astimezone(dt.timezone.utc)
        elif isinstance(v, (bytearray, memoryview)):
            v = bytes(v)
        out.append(v)
    return out


def plain_read(sql, columns):
    """A plain read of one table (SELECT [TOP n] * or [a], [b] FROM [s].[t] [WHERE ...]) with each column
    the driver cannot read written as text: geography, geometry, hierarchyid by .ToString(), sql_variant
    by CAST. `columns`: the table's (name, type) from sys.columns. None when nothing needs it."""
    found = _PLAIN_READ.match(sql or "")
    if not found:
        return None
    kinds = {name.lower(): kind.lower() for name, kind in columns}
    if not any(k in _UDT or k == "sql_variant" for k in kinds.values()):
        return None
    if found.group("columns") == "*":
        wanted = [name for name, _ in columns]
    else:
        named = re.findall(r"\[(?:[^\]]|\]\])+\]", found.group("columns"))
        wanted = [c.strip()[1:-1].replace("]]", "]") for c in named]

    def one(name):
        quoted = "[" + name.replace("]", "]]") + "]"
        kind = kinds.get(name.lower(), "")
        if kind in _UDT:
            return f"{quoted}.ToString() AS {quoted}"
        if kind == "sql_variant":
            return f"CAST({quoted} AS nvarchar(4000)) AS {quoted}"
        return quoted

    top = found.group("top") or ""
    picked = ", ".join(one(c) for c in wanted)
    return f"SELECT {top}{picked} FROM {found.group('object')}{found.group('rest') or ''}"


def is_read(sql):
    """A statement that only reads (SELECT, WITH): safe to run again on a new connection."""
    text = re.sub(r"^\s*(--[^\n]*\n\s*|/\*.*?\*/\s*)*", "", sql or "", flags=re.S)
    return bool(re.match(r"(SELECT|WITH)\b", text, re.I)) and not re.search(r"\bINTO\b", text, re.I)


def managed_identity_token(client_id):
    """The managed identity's token for Azure SQL (Azure's own local request), and when it runs out."""
    query = {"resource": "https://database.windows.net/"}
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
    request = urllib.request.Request(address, None, headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # a local address: no proxy
    try:
        with opener.open(request, timeout=wait) as answer:
            found = json.loads(answer.read())
    except Exception as error:
        raise SqlServerError(
            f"The managed identity's sign-in failed ({error}). It works only inside Azure (a Function App, "
            "App Service or VM) with an identity switched on."
        ) from None
    return found["access_token"], float(found.get("expires_on") or time.time() + 3600)


def app_secret_token(tenant_id, client_id, client_secret):
    """An app registration's token (Microsoft's client credentials request), and when it runs out."""
    login = os.environ.get("SQLSERVER_LOGIN_URL", "https://login.microsoftonline.com")
    form = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://database.windows.net/.default",
    }
    sent = urllib.parse.urlencode(form).encode()
    request = urllib.request.Request(f"{login}/{tenant_id}/oauth2/v2.0/token", sent)
    try:
        with urllib.request.urlopen(request, timeout=60) as answer:
            found = json.loads(answer.read())
    except urllib.error.HTTPError as refused:
        body = refused.read().decode("utf-8", "replace")
        try:
            body = json.loads(body).get("error_description") or body
        except ValueError:
            pass
        first = str(body).strip().splitlines()[0] if str(body).strip() else ""
        raise SqlServerError(
            f"Microsoft Entra refused the app registration ({refused.code}): {first} Check the tenant, the "
            "client id and the client secret."
        ) from None
    return found["access_token"], time.time() + int(found.get("expires_in", 3600))


def cancel(cursor):
    """SQLCancel on a running statement: the cursor's own cancel(), else mssql-python's statement handle."""
    own = getattr(cursor, "cancel", None)
    if callable(own):
        own()
        return
    handle = getattr(cursor, "hstmt", None)
    stop = getattr(handle, "_cancel", None)  # mssql-python: SQLCancel, safe from another thread
    if callable(stop):
        stop()


class Cursor:
    """The driver's cursor, with a statement's errors in plain words, a read run again on a passing
    error, and an interrupt sent to the server (SQLCancel). Everything else is the driver's own."""

    def __init__(self, conn, inner):
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_inner", inner)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __setattr__(self, name, value):
        setattr(self._inner, name, value)  # the driver's own settings

    def __iter__(self):
        return iter(self._inner)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._inner.close()

    def _waited(self, run):
        """`run` while the caller waits: an interrupt meanwhile cancels the statement on the server."""
        done, failed = threading.Event(), []

        def work():
            try:
                run()
            except BaseException as error:  # noqa: BLE001 (handed to the caller)
                failed.append(error)
            finally:
                done.set()

        worker = threading.Thread(target=work, daemon=True, name="sqlserver-statement")
        worker.start()
        try:
            while not done.wait(0.1):
                pass
        except KeyboardInterrupt:
            try:
                cancel(self._inner)  # SQLCancel: the server stops the statement
            finally:
                done.wait(10)
            raise
        if failed:
            raise failed[0]

    def _waited_value(self, run):
        got = []
        self._waited(lambda: got.append(run()))
        return got[0]

    def execute(self, sql, *params):
        conn = self._conn
        rewritten = conn._readable(sql) if not params else None
        statement = rewritten or sql
        for attempt in range(1, conn.TRIES + 1):
            try:
                self._waited(lambda: self._inner.execute(statement, *params))
                return self
            except KeyboardInterrupt:
                raise
            except Exception as error:
                if passing(error) and is_read(statement) and attempt < conn.TRIES:
                    conn._note(f"Try {attempt} met a passing error: read again on a new connection.")
                    conn.sleep(min(2 ** (attempt - 1), 16))
                    conn._reopen()
                    object.__setattr__(self, "_inner", conn._raw.cursor())
                    continue
                raise conn._plain(error) from None
        return self

    def executemany(self, sql, rows):
        try:
            self._waited(lambda: self._inner.executemany(sql, rows))
        except KeyboardInterrupt:
            raise
        except Exception as error:
            raise self._conn._plain(error) from None
        return self


class SqlServer:
    """A SQL Server or Azure SQL database, signed in its own way (see the starter's code below it).

        conn.cursor()             mssql-python's cursor, errors in plain words
        conn.read_arrow(sql)      every row of a query as an Arrow table, each column typed exactly
        conn.about()              the driver, the sign-in, the server's version and edition, collation
        conn.for_writes()         the same connection without read-only intent (the Write starters')
        conn.raw                  the driver's own connection
    """

    dbms = "sqlserver"  # the Write starters know it by this (client/write_sql.py detect)
    TRIES = TRIES_VALUE
    RESUME_SECONDS = RESUME_VALUE
    BATCH_ROWS = 50_000
    sleep = staticmethod(time.sleep)
    clock = staticmethod(time.monotonic)

    def __init__(
        self,
        server,
        database="",
        sign_in="",
        user="",
        password=None,
        token=None,
        credential=None,
        client_id="",
        tenant_id="",
        client_secret=None,
        port=1433,
        instance="",
        encrypt="mandatory",
        trust_server_certificate=False,
        host_name_in_certificate="",
        read_only_intent=False,
        multi_subnet_failover=False,
        login_timeout=30,
        query_timeout=0,
        **older,
    ):
        # older: a setting an older code says that this one does not take (its ODBC driver)
        self.settings = {k: v for k, v in locals().items() if k not in ("self", "older")}
        self.sign_in = sign_in
        self.notes = []
        self._raw = None
        self._token = ("", 0.0)
        self._columns = {}
        self.connect()  # signs in now: Test means it

    # ===== the driver =====

    def driver(self):
        """Microsoft's mssql-python: a pip package with its own driver inside (nothing else to install).
        Missing: the import's own error, which the app turns into its Install prompt."""
        import mssql_python

        return mssql_python

    # ===== the connection string and the sign-in =====

    def connection_string(self):
        """mssql-python's connection string (its keys: no Driver=, which it chooses itself)."""
        s = self.settings
        server = str(s["server"]).strip()
        if s["instance"] and "\\" not in server:
            server = f"{server}\\{s['instance']}"
        elif "," not in server and "\\" not in server and s["port"] and int(s["port"]) != 1433:
            server = f"{server},{int(s['port'])}"
        parts = [f"Server={braced(server)}"]
        if s["database"]:
            parts.append(f"Database={braced(s['database'])}")
        encrypt = str(s["encrypt"] or "mandatory").strip().lower()
        encrypt = {"yes": "mandatory", "true": "mandatory", "no": "optional", "false": "optional"}.get(
            encrypt, encrypt
        )
        parts.append(f"Encrypt={encrypt}")
        if encrypt != "strict":
            parts.append(f"TrustServerCertificate={'yes' if s['trust_server_certificate'] else 'no'}")
        if s["host_name_in_certificate"]:
            parts.append(f"HostNameInCertificate={braced(s['host_name_in_certificate'])}")
        if s["read_only_intent"]:
            parts.append("ApplicationIntent=ReadOnly")
        if s["multi_subnet_failover"]:
            parts.append("MultiSubnetFailover=Yes")
        parts.append("ConnectRetryCount=3")  # an idle connection that dropped is reconnected by the driver
        way = self.sign_in
        if way == "sql_login":
            parts += [f"UID={braced(s['user'])}", password(s["password"])]
        elif way == "windows":
            parts.append("Trusted_Connection=yes")
        elif way == "entra_password":
            parts += ["Authentication=ActiveDirectoryPassword", f"UID={braced(s['user'])}"]
            parts.append(password(s["password"]))
        elif way == "entra_default":
            parts.append("Authentication=ActiveDirectoryDefault")
            if s["user"]:
                parts.append(f"UID={braced(s['user'])}")
        elif way == "entra_integrated":
            parts.append("Authentication=ActiveDirectoryIntegrated")
        return ";".join(parts) + ";"

    def access_token(self):
        """The Entra token, taken again when it has five minutes or less to run."""
        token, expires = self._token
        if not token or time.time() > expires - 300:
            s = self.settings
            if self.sign_in == "managed_identity":
                self._token = managed_identity_token(s["client_id"])
            elif self.sign_in == "app_secret":
                self._token = app_secret_token(s["tenant_id"], s["client_id"], s["client_secret"])
            elif s["credential"] is not None:
                found = s["credential"].get_token("https://database.windows.net/.default")
                self._token = (found.token, float(found.expires_on))
            elif callable(s["token"]):
                self._token = tuple(s["token"]())
            else:
                raise SqlServerError(f"The sign-in {self.sign_in!r} needs a token or a credential.")
        return self._token[0]

    def uses_token(self):
        return self.sign_in in (
            "entra_you", "entra_mfa", "managed_identity", "app_secret", "app_certificate", "token"
        )

    def _open(self):
        driver = self.driver()
        text = self.connection_string()
        # 1256: SQL_COPT_SS_ACCESS_TOKEN, the token beside the connection string
        attrs = {1256: token_struct(self.access_token())} if self.uses_token() else None
        timeout = int(self.settings["login_timeout"] or 0)
        raw = driver.connect(text, attrs_before=attrs, timeout=timeout)
        if self.settings["query_timeout"]:
            try:
                raw.timeout = int(self.settings["query_timeout"])
            except (AttributeError, TypeError):
                pass
        return raw

    def connect(self):
        """Signed in, a passing error tried again (a paused serverless database waited for, said as it
        goes); any other refusal in plain words."""
        started = self.clock()
        attempt = 0
        while True:
            attempt += 1
            try:
                self._raw = self._open()
                return self
            except (SqlServerError, ImportError):  # a missing mssql-python: the app's Install prompt
                raise
            except Exception as error:
                waited = self.clock() - started
                if resuming(error) and waited < self.RESUME_SECONDS:
                    self._note(f"The database is resuming (it was paused): waiting, {int(waited)} s so far.")
                    self.sleep(min(2 ** (attempt - 1), 16, max(1, self.RESUME_SECONDS - waited)))
                    continue
                if passing(error) and not resuming(error) and attempt < self.TRIES:
                    self._note(f"Try {attempt} met a passing error: signing in again.")
                    self.sleep(min(2 ** (attempt - 1), 16))
                    continue
                raise self._plain(error) from None

    def _note(self, words):
        self.notes.append(words)
        print(words, file=sys.stderr, flush=True)

    def _plain(self, error):
        """The driver's error with its meaning and fix first, of the driver's own class (so code that
        catches mssql_python.Error still does)."""
        text = said(error)
        words = explain(text)
        if words == text:
            return error
        try:
            made = type(error)(words, text)  # mssql-python's errors: (driver_error, ddbc_error)
            made.args = (f"{words} [{text}]",)
            return made
        except Exception:
            try:
                return type(error)(f"{words} [{text}]")
            except Exception:
                return SqlServerError(f"{words} [{text}]")

    def _reopen(self):
        self.close()
        self.connect()

    @property
    def raw(self):
        self._fresh()
        return self._raw

    def _fresh(self):
        """Connected, with a token that has time to run: a closed connection or an old token, a new one."""
        if self._raw is None or (self.uses_token() and time.time() > self._token[1] - 300):
            self._reopen()

    # ===== shaped like the driver's connection =====

    def cursor(self):
        self._fresh()
        return Cursor(self, self._raw.cursor())

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        if self._raw is not None:
            try:
                self._raw.close()
            except Exception:  # noqa: S110 (already closed, or the connection dropped)
                pass
            self._raw = None

    def __getattr__(self, name):
        if name.startswith("_") or name == "settings":
            raise AttributeError(name)
        return getattr(self.raw, name)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def for_writes(self):
        """This connection for a write: read-only intent goes (a read replica refuses writes)."""
        if not self.settings["read_only_intent"]:
            return self
        settings = dict(self.settings)
        settings["read_only_intent"] = False
        return SqlServer(**settings)

    # ===== reads =====

    def _readable(self, sql):
        """A plain read of one table rewritten so the driver can read every column (plain_read)."""
        found = _PLAIN_READ.match(sql or "")
        if not found:
            return None
        name = found.group("object")
        if name not in self._columns:
            cursor = self._raw.cursor()
            try:
                cursor.execute(
                    "SELECT c.name, t.name FROM sys.columns AS c JOIN sys.types AS t ON t.user_type_id = "
                    "c.user_type_id WHERE c.object_id = OBJECT_ID(?) ORDER BY c.column_id",
                    name,
                )
                self._columns[name] = [(str(r[0]), str(r[1])) for r in cursor.fetchall()]
            except Exception:
                self._columns[name] = []
            finally:
                cursor.close()
        return plain_read(sql, self._columns[name])

    def read_arrow(self, sql, batch_rows=None):
        """Every row the query answers as an Arrow table: mssql-python's own Arrow batches where it reads
        every column (arrow_typed: the same types as below), else fetched in batches, each column's
        type from the driver's description (arrow_type). A column whose values do not fit its type is
        text."""
        pa = importlib.import_module("pyarrow")  # the app's own Python has it

        cursor = self.cursor()
        try:
            cursor.execute(sql)
            if cursor.description is None:
                raise SqlServerError("The statement returned no rows to read.")
            described = list(cursor.description)
            native = getattr(cursor._inner, "arrow_batch", None)
            if callable(native):
                try:
                    batches = []
                    while True:
                        batch = cursor._waited_value(lambda: native(batch_rows or self.BATCH_ROWS))
                        if batch.num_rows or not batches:
                            batches.append(batch)
                        if batch.num_rows < (batch_rows or self.BATCH_ROWS):
                            break
                    return arrow_typed(pa, pa.Table.from_batches(batches, schema=batches[0].schema))
                except KeyboardInterrupt:
                    raise
                except Exception as error:
                    if "Arrow" not in said(error) or not is_read(sql):
                        raise self._plain(error) from None
                    cursor.close()  # a column it cannot read as Arrow (sql_variant): rows, then Arrow
                    cursor = self.cursor()
                    cursor.execute(sql)
                    described = list(cursor.description)
            names = [str(d[0]) for d in described]
            types, chunks = None, [[] for _ in names]
            while True:
                rows = cursor.fetchmany(batch_rows or self.BATCH_ROWS)
                if not rows:
                    break
                columns = list(zip(*rows))
                if types is None:
                    types = [
                        arrow_type(pa, d[1], d[3], d[4], d[5], columns[i]) for i, d in enumerate(described)
                    ]
                for i, values in enumerate(columns):
                    values = arrow_values(values, described[i][1])
                    try:
                        chunks[i].append(pa.array(values, types[i]))
                    except (pa.ArrowInvalid, pa.ArrowTypeError, OverflowError, TypeError, ValueError):
                        types[i] = pa.string()
                        chunks[i] = [c.cast(pa.string()) for c in chunks[i]]
                        text = [None if v is None else str(v) for v in values]
                        chunks[i].append(pa.array(text, pa.string()))
            if types is None:
                types = [arrow_type(pa, d[1], d[3], d[4], d[5], ()) for d in described]
            arrays = [pa.chunked_array(chunks[i], types[i]) for i in range(len(names))]
            return pa.Table.from_arrays(arrays, names=names)
        finally:
            cursor.close()

    def about(self):
        """What the card says: the driver, the sign-in, the server's version and edition, and its
        collation (a case-sensitive one matters for joins in DuckDB). Names and words only."""
        found = {"driver": "mssql-python", "sign_in": self.sign_in}
        cursor = self.raw.cursor()
        try:
            cursor.execute(
                "SELECT @@VERSION, CAST(SERVERPROPERTY('Edition') AS nvarchar(128)), "
                "CAST(DATABASEPROPERTYEX(DB_NAME(), 'Collation') AS nvarchar(128)), "
                "CAST(DATABASEPROPERTYEX(DB_NAME(), 'ServiceObjective') AS nvarchar(128))"
            )
            version, edition, collation, objective = cursor.fetchone()
            found["version"] = str(version or "").splitlines()[0].strip()
            found["edition"] = str(edition or "")
            if objective:
                found["service_objective"] = str(objective)
            if collation:
                found["collation"] = str(collation)
                found["case_sensitive"] = "_CS_" in f"{collation}_" or str(collation).endswith("_BIN2")
        except Exception:  # noqa: S110 (a server that will not say: the card says less)
            pass
        finally:
            cursor.close()
        return found

    def tested(self, rows=20):
        """Test connection's answer: signed in, and what the server is (about)."""
        return {"found": "signed in", "about": self.about(), "notes": list(self.notes)}
'''.replace("ERRORS_JSON", repr(json.dumps(ERRORS)))
    .replace("TRANSIENT_JSON", repr(sorted(TRANSIENT)))
    .replace("WORDS_JSON", repr(json.dumps(WORDS)))
    .replace("DROPPED_JSON", repr(json.dumps(DROPPED)))
    .replace("NOT_FOUND_JSON", repr(json.dumps(NOT_FOUND)))
    .replace("TRIES_VALUE", str(TRIES))
    .replace("RESUME_VALUE", str(RESUME_SECONDS))
)

# ===== each way to sign in: the code around the call =====

AZURE_SERVER = "my-server.database.windows.net"

# (key, label, the azure-identity import, the lines before the call, the call's sign-in keywords)
_WAYS: dict[str, tuple[str, str, str, str]] = {
    "sql_login": (
        "User name and password (SQL login)",
        "",
        "",
        '    user="my_user",\n    password=secret("password"),\n',
    ),
    "windows": ("Windows sign-in", "", "", ""),
    "entra_you": (
        "Microsoft Entra: as you (Azure command line, else a browser)",
        "from azure.identity import AzureCliCredential, ChainedTokenCredential, "
        "InteractiveBrowserCredential\n",
        "# Signed in as you: the Azure command line (az login), else a browser window.\n"
        'tenant_id = ""  # empty: your own tenant\n'
        "credential = ChainedTokenCredential(\n"
        "    AzureCliCredential(tenant_id=tenant_id or None),\n"
        "    InteractiveBrowserCredential(tenant_id=tenant_id or None),\n)\n\n",
        "    credential=credential,\n",
    ),
    "entra_mfa": (
        entra.MFA_LABEL,
        "",
        "# Signed in as you with multi-factor sign-in: a browser window with your username filled in\n"
        "# (or, where none can open, a code to type on another device), remembered afterwards. The token\n"
        "# goes beside the connection string (mssql-python's own ActiveDirectoryInteractive neither fills\n"
        "# in the username nor remembers the sign-in outside Windows: it would ask for MFA every run).\n"
        + entra.MFA_CLASS.lstrip("\n")
        + "\n\n"
        'credential = MultiFactorSignIn(tenant_id="my-tenant-id", username="my_user@my-company.com")\n\n',
        "    credential=credential,\n",
    ),
    "managed_identity": (
        "Microsoft Entra: managed identity (in Azure)",
        "",
        "",
        '    client_id="",  # a user-assigned identity\'s client id; empty: the system identity\n',
    ),
    "app_secret": (
        "Microsoft Entra: app registration, its secret from a key vault",
        "",
        "",
        '    tenant_id="my-tenant-id",\n    client_id="my-client-id",\n'
        '    client_secret=secret("client secret"),\n',
    ),
    "app_certificate": (
        "Microsoft Entra: app registration with a certificate",
        "from azure.identity import CertificateCredential\n",
        "# An app registration that signs in with its certificate (a .pem holding the key).\n"
        "credential = CertificateCredential(\n"
        '    tenant_id="my-tenant-id",\n    client_id="my-client-id",\n'
        '    certificate_path=r"C:\\certs\\my-app.pem",\n)\n\n',
        "    credential=credential,\n",
    ),
    "entra_password": (
        "Microsoft Entra: user name and password",
        "",
        "",
        '    user="my_user@my-company.com",\n    password=secret("password"),\n',
    ),
    "entra_default": (
        "Microsoft Entra: the driver's default (a managed identity in Azure)",
        "import azure.identity  # noqa: F401 (mssql-python signs in with it: ActiveDirectoryDefault)\n",
        "",
        "",
    ),
}
# Each template's ways, its first the starter's own.
# The first is a way that runs on an Azure Function App or a hosted Streamlit app as well as here (the owner,
# 2026-11-17: "we want to advise against any connectors that only work locally"); this machine's only ways
# (domain/portability.py) come last. A saved connection keeps the way its code says.
ORDER: dict[str, tuple[str, ...]] = {
    "sqlserver": (
        "sql_login",
        "managed_identity",
        "app_secret",
        "entra_default",
        "entra_password",
        "entra_mfa",
        "windows",
        "entra_you",
        "app_certificate",
    ),
    "azuresql": (
        "app_secret",
        "managed_identity",
        "sql_login",
        "entra_default",
        "entra_password",
        "entra_mfa",
        "entra_you",
        "app_certificate",
    ),
}


def code(way: str, server: str = "my-server") -> str:
    """The connection's code for one way to sign in: the imports, the runtime, then `conn = SqlServer(...)`
    with every setting the form shows as a keyword (or, for a credential's tenant, a name)."""
    _, imports, before, keywords = _WAYS[way]
    return (
        _IMPORTS
        + (f"\n{imports}" if imports else "")
        + RUNTIME
        + "\n\n"
        + before
        + "conn = SqlServer(\n"
        + f'    server="{server}",\n'
        + '    database="my_database",\n'
        + f'    sign_in="{way}",\n'
        + keywords
        + "    port=1433,\n"
        + '    instance="",  # a named instance (server\\instance): its name\n'
        + '    encrypt="mandatory",  # mandatory, optional or strict\n'
        + "    trust_server_certificate=False,\n"
        + '    host_name_in_certificate="",\n'
        + "    read_only_intent=True,  # reads ask for a read replica where there is one (writes do not)\n"
        + "    multi_subnet_failover=False,\n"
        + "    login_timeout=30,\n"
        + "    query_timeout=0,  # seconds; 0: no limit\n"
        + ")"
    )


def mark(way: str) -> str:
    """The text only this way's code holds (the form tells which way a saved connection signs in)."""
    return f'sign_in="{way}"'


def sign_ins(template: str) -> tuple[tuple[str, str, str], ...]:
    """The form's Sign in for a template: (label, mark, code), the first the starter's own code."""
    server = AZURE_SERVER if template == "azuresql" else "my-server"
    return tuple((_WAYS[w][0], mark(w), code(w, server)) for w in ORDER[template])


def way_of(text: str) -> str | None:
    """Which way a connection's code signs in (its sign_in="..."), or None for code of another shape."""
    found = re.search(r'\bsign_in\s*=\s*"([a-z_]+)"', text)
    return found.group(1) if found and found.group(1) in _WAYS else None


def label_of(way: str) -> str:
    return _WAYS[way][0] if way in _WAYS else way


# The form: these settings may come from an environment variable (the owner, 2026-11-17), these are
# folded under Options, and these offer a choice.
ENV_SETTINGS: tuple[str, ...] = ("server", "database", "user", "client_id", "tenant_id")
# The keywords the code says them with, and their plain names (domain/blades.py KEYWORDS takes these).
KEYWORDS: dict[str, str] = {
    "driver": "driver",
    "instance": "instance",
    "encrypt": "encryption",
    "host_name_in_certificate": "host name in certificate",
    "read_only_intent": "read only intent",
    "multi_subnet_failover": "multi subnet failover",
    "login_timeout": "login timeout",
    "query_timeout": "query timeout",
    "client_id": "client_id",  # an app registration's ids, named as the code names them (Power BI's too)
    "tenant_id": "tenant_id",
    "certificate_path": "client certificate file",
}
FLAGS: frozenset[str] = frozenset({"read only intent", "multi subnet failover"})
OPTIONS: tuple[str, ...] = (
    "port",
    "instance",
    "encryption",
    "trust server certificate",
    "host name in certificate",
    "read only intent",
    "multi subnet failover",
    "login timeout",
    "query timeout",
)
CHOICES: dict[str, tuple[str, ...]] = {
    "encryption": ("mandatory", "optional", "strict"),
}


def is_robust(code_text: str) -> bool:
    """Whether a connection's code is this module's (a SqlServer object), not a plain one of its own."""
    return "class SqlServer:" in code_text and way_of(code_text) is not None


# ===== an older code, on pyodbc: Update to the new driver =====

_OLD_END = 'return {"found": "signed in", "about": self.about(), "notes": list(self.notes)}'
_OLD_DRIVER = re.compile(r"^[ \t]*driver\s*=\s*(\"[^\"\n]*\"|'[^'\n]*')\s*,[^\n]*\n", re.MULTILINE)


def is_old(code_text: str) -> bool:
    """Whether a connection's code is this module's earlier one, on pyodbc and an ODBC driver: a starter's
    code the app made (its SqlServer runtime, its sign_in), so it may be made again on mssql-python. A
    connection of the user's own (any other code) is never one."""
    if not is_robust(code_text) or _OLD_END not in code_text:
        return False
    head = code_text[: code_text.index(_OLD_END)]
    return "import pyodbc" in head and "pyodbc.drivers()" in head


# As you's imports before 2026-11-20, when its chain held VisualStudioCodeCredential (azure-identity's works
# only on Windows with azure-identity-broker, so it left the chain; an older code keeps its own lines).
_OLDER_YOU_IMPORTS = (
    "from azure.identity import (\n    AzureCliCredential,\n    ChainedTokenCredential,\n"
    "    InteractiveBrowserCredential,\n    VisualStudioCodeCredential,\n)\n"
)


def upgraded(code_text: str) -> str:
    """An older code made again on mssql-python with the same settings: its head (the imports its way
    needs and the runtime) is today's, its own lines after the runtime (the credential,
    `conn = SqlServer(...)` with every setting the user gave) kept as they are, but for the driver=
    setting, which mssql-python does not take. Refused (ValueError) for any code is_old does not know."""
    if not is_old(code_text):
        raise ValueError("This connection's code is not the earlier SQL Server code the app made.")
    at = code_text.index(_OLD_END) + len(_OLD_END)
    tail = code_text[at:]
    imports = _WAYS[str(way_of(code_text))][1]  # the way's own imports, as its code() has them
    if "VisualStudioCodeCredential(" in tail:  # as you, before 2026-11-20: its chain kept as the user had it
        imports = _OLDER_YOU_IMPORTS
    tail = _OLD_DRIVER.sub("", tail)
    runtime = RUNTIME[: RUNTIME.index(_OLD_END) + len(_OLD_END)]
    return _IMPORTS + (f"\n{imports}" if imports else "") + runtime + tail


# ===== the catalog: the system views =====

CATALOG = """SELECT DB_NAME() AS table_catalog, s.name AS table_schema, o.name AS table_name,
       CASE o.type WHEN 'V' THEN 'VIEW' WHEN 'SN' THEN 'VIEW' ELSE 'BASE TABLE' END AS table_type,
       c.name AS column_name,
       CASE
         WHEN t.name IN ('varchar', 'char', 'varbinary', 'binary')
           THEN t.name + '('
             + CASE c.max_length WHEN -1 THEN 'max' ELSE CAST(c.max_length AS varchar(5)) END + ')'
         WHEN t.name IN ('nvarchar', 'nchar')
           THEN t.name + '('
             + CASE c.max_length WHEN -1 THEN 'max' ELSE CAST(c.max_length / 2 AS varchar(5)) END + ')'
         WHEN t.name IN ('decimal', 'numeric')
           THEN t.name + '(' + CAST(c.precision AS varchar(3)) + ',' + CAST(c.scale AS varchar(3)) + ')'
         WHEN t.name IN ('datetime2', 'datetimeoffset', 'time')
           THEN t.name + '(' + CAST(c.scale AS varchar(3)) + ')'
         ELSE t.name
       END AS data_type,
       CASE c.is_nullable WHEN 1 THEN 'YES' ELSE 'NO' END AS is_nullable,
       c.column_id AS ordinal_position,
       NULLIF(LTRIM(CONCAT(
         CASE WHEN pk.column_id IS NOT NULL THEN ' Primary key.' END,
         CASE WHEN c.is_identity = 1 THEN ' Identity.' END,
         CASE WHEN c.is_computed = 1 THEN ' Computed.' END,
         CASE WHEN c.is_sparse = 1 THEN ' Sparse.' END,
         CASE WHEN c.generated_always_type > 0 THEN ' Period column.' END,
         ' ' + CAST(ep.value AS nvarchar(4000)))), '') AS description
FROM sys.objects AS o
JOIN sys.schemas AS s ON s.schema_id = o.schema_id
LEFT JOIN sys.synonyms AS sn ON sn.object_id = o.object_id
JOIN sys.columns AS c ON c.object_id = CASE
  WHEN sn.object_id IS NULL THEN o.object_id
  WHEN COALESCE(PARSENAME(sn.base_object_name, 3), DB_NAME()) = DB_NAME() THEN OBJECT_ID(sn.base_object_name)
END  -- a synonym: its object's columns, when the object is in this database
JOIN sys.types AS t ON t.user_type_id = c.user_type_id
LEFT JOIN (
  SELECT ic.object_id, ic.column_id FROM sys.indexes AS i
  JOIN sys.index_columns AS ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
  WHERE i.is_primary_key = 1
) AS pk ON pk.object_id = c.object_id AND pk.column_id = c.column_id
LEFT JOIN sys.extended_properties AS ep
  ON ep.class = 1 AND ep.major_id = c.object_id AND ep.minor_id = c.column_id AND ep.name = 'MS_Description'
WHERE o.type IN ('U', 'V', 'SN') AND o.is_ms_shipped = 0
UNION ALL
SELECT DB_NAME(), s.name, o.name, CASE o.type WHEN 'V' THEN 'VIEW' ELSE 'BASE TABLE' END, '', '', 'YES', 0,
       NULLIF(STUFF(CONCAT(
         CASE WHEN o.type = 'U' THEN N' · ' + FORMAT(COALESCE(r.n, 0), 'N0') + N' rows' END,
         CASE WHEN tb.temporal_type = 2 THEN N' · temporal (history: ' + hs.name + N'.' + h.name + N')' END,
         CASE WHEN tb.temporal_type = 1 THEN N' · history table' END,
         N' · ' + CAST(ep.value AS nvarchar(4000))), 1, 3, N''), N'')
FROM sys.objects AS o
JOIN sys.schemas AS s ON s.schema_id = o.schema_id
LEFT JOIN sys.tables AS tb ON tb.object_id = o.object_id
LEFT JOIN sys.tables AS h ON h.object_id = tb.history_table_id
LEFT JOIN sys.schemas AS hs ON hs.schema_id = h.schema_id
LEFT JOIN (
  SELECT object_id, SUM(rows) AS n FROM sys.partitions WHERE index_id IN (0, 1) GROUP BY object_id
) AS r ON r.object_id = o.object_id
LEFT JOIN sys.extended_properties AS ep
  ON ep.class = 1 AND ep.major_id = o.object_id AND ep.minor_id = 0 AND ep.name = 'MS_Description'
WHERE o.type IN ('U', 'V') AND o.is_ms_shipped = 0
ORDER BY 2, 3, 8"""


# A server that takes only part of SQL Server's language (Dataverse's SQL endpoint: "Unsupported sql
# function PARSENAME"; the owner, 2026-11-20) cannot run CATALOG: its tables are listed from
# INFORMATION_SCHEMA instead, which every SQL Server-speaking endpoint has (no rows, no descriptions).
PLAIN_CATALOG = """SELECT TABLE_CATALOG AS table_catalog, TABLE_SCHEMA AS table_schema,
       TABLE_NAME AS table_name, 'BASE TABLE' AS table_type, COLUMN_NAME AS column_name,
       DATA_TYPE AS data_type, IS_NULLABLE AS is_nullable, ORDINAL_POSITION AS ordinal_position
FROM INFORMATION_SCHEMA.COLUMNS
ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION"""


def plain_catalog_for(command: str) -> str | None:
    """The plainer listing to try when `command` (the rich SQL Server catalog) fails; None for any other."""
    return PLAIN_CATALOG if command.strip() == CATALOG.strip() else None


def count_sql(schema: str, table: str) -> str:
    """A table's rows from sys.partitions (no COUNT(*) over the table); a view's are counted."""
    name = ".".join(quote_identifier(p, "sqlserver") for p in (schema, table) if p)
    literal = "N'" + name.replace("'", "''") + "'"
    return (
        f"SELECT CASE WHEN OBJECTPROPERTY(OBJECT_ID({literal}), 'IsUserTable') = 1\n"  # noqa: S608 (quoted)
        f"  THEN (SELECT SUM(p.rows) FROM sys.partitions AS p WHERE p.object_id = OBJECT_ID({literal}) "
        "AND p.index_id IN (0, 1))\n"
        f"  ELSE (SELECT COUNT_BIG(*) FROM {name}) END"
    )


# ===== foreign keys into the ERD =====

FOREIGN_KEYS = """SELECT fk.name AS name, ps.name AS from_schema, pt.name AS from_table,
       pc.name AS from_column,
       rs.name AS to_schema, rt.name AS to_table, rc.name AS to_column, fkc.constraint_column_id AS position,
       fk.is_disabled AS disabled
FROM sys.foreign_keys AS fk
JOIN sys.foreign_key_columns AS fkc ON fkc.constraint_object_id = fk.object_id
JOIN sys.tables AS pt ON pt.object_id = fk.parent_object_id
JOIN sys.schemas AS ps ON ps.schema_id = pt.schema_id
JOIN sys.columns AS pc ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id
JOIN sys.tables AS rt ON rt.object_id = fk.referenced_object_id
JOIN sys.schemas AS rs ON rs.schema_id = rt.schema_id
JOIN sys.columns AS rc ON rc.object_id = fkc.referenced_object_id AND rc.column_id = fkc.referenced_column_id
ORDER BY fk.name, fkc.constraint_column_id"""

UNIQUE_KEYS = """SELECT s.name AS table_schema, t.name AS table_name, i.name AS index_name,
       c.name AS column_name
FROM sys.indexes AS i
JOIN sys.index_columns AS ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
JOIN sys.columns AS c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
JOIN sys.tables AS t ON t.object_id = i.object_id
JOIN sys.schemas AS s ON s.schema_id = t.schema_id
WHERE i.is_unique = 1 AND ic.is_included_column = 0
ORDER BY s.name, t.name, i.name, ic.key_ordinal"""

RELATIONSHIP_QUERIES: tuple[tuple[str, ...], ...] = ((FOREIGN_KEYS, UNIQUE_KEYS),)


class SqlServerError(ValueError):
    """The database's answer cannot be read as relationships (the message says why)."""


def _rows(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    names = [str(c).lower() for c in result.get("columns") or []]
    return [dict(zip(names, row, strict=False)) for row in result.get("rows") or []]


def grid_name(table: str) -> str:
    """A table as it opens as a grid (domain/connections.py dataset_name, which this mirrors)."""
    bare = re.sub(r"\.[A-Za-z0-9]{1,8}$", "", table.strip())
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", bare).strip("_")[:64]
    return name or "table"


def relationships_model(connection: str, results: Sequence[Mapping[str, Any]], model: str = "") -> Model:
    """The database's foreign keys as a model to merge (composite keys kept whole): many-to-one from the
    referencing table to the referenced one, one-to-one when the referencing columns are themselves a
    unique key. A disabled foreign key comes inactive. Tables are named as they open as grids."""
    from swissarmybench.domain.relationships import Model, Relationship, parse_model

    if not results:
        raise SqlServerError("The database gave no answer for its foreign keys.")
    keys: dict[str, list[dict[str, Any]]] = {}
    for row in _rows(results[0]):
        keys.setdefault(str(row.get("name") or ""), []).append(row)
    unique: set[tuple[str, str, tuple[str, ...]]] = set()
    if len(results) > 1:
        indexes: dict[tuple[str, str, str], list[str]] = {}
        for row in _rows(results[1]):
            key = (str(row["table_schema"]), str(row["table_name"]), str(row["index_name"]))
            indexes.setdefault(key, []).append(str(row["column_name"]))
        unique = {(s, t, tuple(sorted(c.lower() for c in cols))) for (s, t, _), cols in indexes.items()}
    found: list[Relationship] = []
    for name, columns in keys.items():
        columns.sort(key=lambda r: int(r.get("position") or 0))
        first = columns[0]
        from_columns = tuple(str(r["from_column"]) for r in columns)
        one = (
            str(first["from_schema"]),
            str(first["from_table"]),
            tuple(sorted(c.lower() for c in from_columns)),
        )
        found.append(
            Relationship(
                grid_name(str(first["from_table"])),
                from_columns,
                grid_name(str(first["to_table"])),
                tuple(str(r["to_column"]) for r in columns),
                "one-to-one" if one in unique else "many-to-one",
                f"foreign key {name}" if name else "",
                not _true(first.get("disabled")),
            )
        )
    tables = {t for r in found for t in (r.from_table, r.to_table)}
    built = Model(
        name=model or f"{connection} foreign keys",
        sources={t: f"connection:{connection}" for t in sorted(tables)},
        relationships=tuple(found),
    )
    return parse_model(built.to_json())


def _true(value: object) -> bool:
    return value is True or str(value).strip().lower() in ("1", "true", "yes")


# ===== the card =====


def card_words(about: Mapping[str, Any]) -> list[str]:
    """What a SQL Server card says of the server (about()): the driver and sign-in, the version and
    edition (Azure's service objective), and a case-sensitive collation said once."""
    lines: list[str] = []
    driver, way = str(about.get("driver") or ""), str(about.get("sign_in") or "")
    if driver or way:
        lines.append(" · ".join(p for p in (driver, label_of(way) if way else "") if p))
    version = str(about.get("version") or "")
    edition = str(about.get("edition") or "")
    objective = str(about.get("service_objective") or "")
    shown = " · ".join(p for p in (version, edition, objective) if p)
    if shown:
        lines.append(shown)
    if about.get("case_sensitive"):
        lines.append(f"Case-sensitive collation ({about.get('collation')})")  # joins: as in DuckDB
    return lines


def choices_for(name: str) -> list[str]:
    return list(CHOICES.get(name, ()))


def env_mappable(template: str | None) -> list[str]:
    return list(ENV_SETTINGS) if template in TEMPLATES else []


def options(template: str | None) -> list[str]:
    return list(OPTIONS) if template in TEMPLATES else []
