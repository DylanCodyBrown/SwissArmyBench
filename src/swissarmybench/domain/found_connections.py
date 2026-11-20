"""Find connections on this computer (the owner, 2026-11-20: "Is it possible to scan the computer's common
apps for connections and import them. DBeaver, SSMS, ODBC, etc." / "You could scan the app directory for
hints of what to search for.").

Two ways in, both read-only and both on the user's click only:

  the known tools, read exactly   domain/found_readers.py: ODBC data sources, SSMS, DBeaver, Azure Data
                                  Studio, VS Code (mssql, SQLTools), JetBrains, pgAdmin 4, MySQL Workbench,
                                  HeidiSQL, Office's .odc and .udl, each file's text to its connections
  the hint scan                   the same file's `hints`: small text files under the app settings folders,
                                  looked through for connection-shaped strings

Here: what a found connection is (Found, Source; kinds), the parts tools write one in (connection_pairs,
parse_url, from_object), passwords cut out (`clean`), the list and the import.

**Passwords are never kept.** A Found has no field for one: each reader takes only the named parts (the
server, the port, the database, the user) and a URL's user:password@ keeps only the user; `clean` cuts any
Password=, Pwd= or user:password@ text out of every string before a reader answers.

Then the list: the same connection found in several tools is one row (`merge`: its kind's family, its server,
its database, or its file or data source), every source shown; one the library has already is "Already
added" (`found_from_settings`); a kind Swiss Army Bench has no connection for is shown, never tickable.
Import makes each ticked row a connection from its starter's code (`connection_body`), its password a
variable it names.

Pure: no I/O (the adapter reads; the service keeps the last scan and saves).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from swissarmybench.domain import blades as blade_rules
from swissarmybench.domain import connections as connection_rules

# ===== what a found connection is =====


@dataclass(frozen=True)
class Source:
    """Where one was found: the tool (DBeaver) or, for the hint scan, the program's folder."""

    tool: str
    where: str = ""  # the folder in words, from the home folder (AppData\Roaming\DBeaverData\workspace6)
    searched: bool = False  # found by searching (the hint scan), not read from a tool's own list

    def to_json(self) -> dict[str, Any]:
        return {"tool": self.tool, "where": self.where, "searched": self.searched}


@dataclass(frozen=True)
class Found:
    """One connection a tool keeps. Never a password: there is no field for one."""

    kind: str  # a starter's id where we have one (sqlserver, postgres...), else the kind in a word (mongodb)
    name: str = ""
    server: str = ""
    port: int | None = None
    database: str = ""
    user: str = ""
    windows: bool = False  # signs in as this computer's Windows account (integrated security)
    instance: str = ""  # SQL Server's named instance
    dsn: str = ""  # an ODBC data source's name
    path: str = ""  # a file database's path (SQLite, Access, DuckDB)
    sources: tuple[Source, ...] = ()


# ===== kinds =====

# A kind from the words a tool uses for it (a driver's or provider's name, a URL's scheme), first match wins.
_KIND_WORDS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (kind, re.compile(pattern, re.IGNORECASE))
    for kind, pattern in (
        ("access", r"\baccess\b|\bace\.oledb|jet\.oledb|\.accdb\b|\.mdb\b|\bmsaccess"),
        ("analysisservices", r"msolap|analysis ?services"),
        ("sybase", r"sybase|adaptive server|\base\b"),
        ("azuresql", r"azure ?sql|database\.windows\.net"),
        ("sqlserver", r"sql ?server|sqlserver|mssql|sqloledb|msoledbsql|sqlncli|sqlsrv|jtds|\bmsodbcsql"),
        ("mariadb", r"maria"),
        ("mysql", r"mysql"),
        ("redshift", r"redshift"),
        ("postgres", r"postgres|pgsql|psql|npgsql|greenplum|cockroach|\bpg\b"),
        ("oracle", r"oracle|oraoledb|\bora\b|\boci\b"),
        ("snowflake", r"snowflake"),
        ("db2", r"\bdb2|\bibm\b"),
        ("teradata", r"teradata"),
        ("vertica", r"vertica"),
        ("clickhouse", r"clickhouse|\bch\b"),
        ("trino", r"trino|presto"),
        ("saphana", r"hana|\bsap\b"),
        ("duckdb", r"duckdb"),
        ("sqlite", r"sqlite"),
        ("databricks", r"databricks|simba ?spark|\bspark\b"),
        ("bigquery", r"bigquery"),
        ("mongodb", r"mongo"),
        ("cassandra", r"cassandra"),
        ("redis", r"redis"),
        ("elasticsearch", r"elastic"),
        ("firebird", r"firebird"),
        ("interbase", r"interbase"),
        ("informix", r"informix"),
        ("netezza", r"netezza"),
        ("exasol", r"exasol"),
        ("h2", r"^h2\b|\bh2[_:]|jdbc:h2"),
        ("derby", r"derby"),
        ("hsqldb", r"hsql"),
        ("neo4j", r"neo4j"),
    )
)
# The kinds Swiss Army Bench makes a connection for: each a starter's id (server/blade_templates.py).
SUPPORTED: frozenset[str] = frozenset(
    {
        "sqlserver",
        "azuresql",
        "postgres",
        "mysql",
        "mariadb",
        "oracle",
        "sqlite",
        "duckdb",
        "snowflake",
        "redshift",
        "db2",
        "teradata",
        "trino",
        "clickhouse",
        "saphana",
        "vertica",
        "sybase",
        "access",
        "odbc",
        "databricks",
    }
)
# The others in words (the row says "Swiss Army Bench has no <kind> connection yet").
KIND_NAMES: dict[str, str] = {
    "analysisservices": "Analysis Services",
    "bigquery": "BigQuery",
    "mongodb": "MongoDB",
    "cassandra": "Cassandra",
    "redis": "Redis",
    "elasticsearch": "Elasticsearch",
    "firebird": "Firebird",
    "interbase": "InterBase",
    "informix": "Informix",
    "netezza": "Netezza",
    "exasol": "Exasol",
    "h2": "H2",
    "derby": "Derby",
    "hsqldb": "HSQLDB",
    "neo4j": "Neo4j",
    "unknown": "a database of an unknown kind",
}
# A kind told by its usual port alone (an object with a host, a port and a database, nothing else said).
_PORT_KINDS: dict[int, str] = {
    1433: "sqlserver",
    5432: "postgres",
    3306: "mysql",
    1521: "oracle",
    50000: "db2",
    5433: "vertica",
    5439: "redshift",
    8123: "clickhouse",
    27017: "mongodb",
    6379: "redis",
    9042: "cassandra",
    30015: "saphana",
}
# A kind's family for telling one connection from another (the same server and database is one row).
_FAMILY: dict[str, str] = {"azuresql": "sqlserver", "mariadb": "mysql"}
FILE_KINDS = frozenset({"sqlite", "duckdb", "access"})


def kind_from(text: Any) -> str:
    """A kind from a tool's words for it ("PostgreSQL", "org.postgresql.Driver", "mssql+pyodbc"); "" when
    none is told."""
    if not isinstance(text, str) or not text.strip():
        return ""
    return next((kind for kind, pattern in _KIND_WORDS if pattern.search(text)), "")


def _final_kind(found: Found) -> Found:
    """Azure SQL told by its address; a kind not told at all, by its port."""
    kind = found.kind
    if kind == "sqlserver" and found.server.casefold().rstrip(".").endswith(".database.windows.net"):
        kind = "azuresql"
    if not kind and found.port in _PORT_KINDS:
        kind = _PORT_KINDS[found.port]
    return replace(found, kind=kind or "unknown")


def kind_words(kind: str, labels: Mapping[str, str]) -> str:
    return labels.get(kind) or KIND_NAMES.get(kind) or kind


# ===== passwords never leave a reader =====

# A key that names a secret: never read, whatever its value.
_SECRET_KEY = re.compile(
    r"pass|pwd|secret|token|credential|api_?key|private|auth_?key|access_?key|sas", re.IGNORECASE
)
_IN_TEXT = re.compile(
    r"""(?ix)
    (?P<pair>\b(?:password|pwd|passwd|pass|secret|token|access[ _]?token|api[ _]?key|account[ _]?key)\s*=\s*
       (?:\{[^}]*\}|"[^"]*"|'[^']*'|[^;&,\s"'<>]*))
    | (?P<url>(?<=://)[^:/@\s"'<>]*:[^@/\s"'<>]*@)
    """
)


def is_secret_key(key: Any) -> bool:
    """A key whose value is never read (Password, PWD, client_secret, accessToken...)."""
    return isinstance(key, str) and bool(_SECRET_KEY.search(key))


def scrub(text: str) -> str:
    """Any Password=..., Pwd=... or user:password@ cut out of a text."""
    if not text:
        return text

    def cut(m: re.Match[str]) -> str:
        if m.group("url"):
            return m.group("url").split(":", 1)[0] + "@"
        return ""

    return _IN_TEXT.sub(cut, text)


def clean(found: Found) -> Found:
    """The found connection with every text field scrubbed, its port a number in range and its kind final."""

    def cut(text: str) -> str:
        return scrub(str(text))[:400].strip()

    port = found.port if isinstance(found.port, int) and 0 < found.port < 65536 else None
    plain = replace(
        found,
        port=port,
        name=cut(found.name),
        server=cut(found.server),
        database=cut(found.database),
        user=cut(found.user),
        instance=cut(found.instance),
        dsn=cut(found.dsn),
        path=cut(found.path),
    )
    return _final_kind(plain)


# ===== the parts a tool writes a connection in =====

SERVER_KEYS = (
    "server",
    "data source",
    "datasource",
    "address",
    "addr",
    "network address",
    "host",
    "hostname",
    "servername",
    "server name",
    "dbhost",
)
DATABASE_KEYS = ("database", "initial catalog", "dbname", "db", "database name", "databasename", "schema")
USER_KEYS = ("uid", "user id", "userid", "user", "username", "user name", "lastuser", "login", "dbuser")
TRUE_WORDS = frozenset({"yes", "true", "sspi", "1", "on"})
PLACEHOLDER = re.compile(
    r"""(?ix)^$|[<>{}$%]|\$\{|^(?:host|hostname|server|servername|your[-_ ]?\w*|my[-_]\w*|example(?:\.\w+)*
    |\w+\.example(?:\.\w+)?|xxx+|\*+|placeholder|todo|changeme|db_?host|database_?host)$"""
)


def norm_key(key: str) -> str:
    return " ".join(key.strip().casefold().split())


def first_of(pairs: Mapping[str, str], keys: Iterable[str]) -> str:
    return next((pairs[k].strip() for k in keys if pairs.get(k, "").strip()), "")


def port_of(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def connection_pairs(text: str) -> dict[str, str]:
    """An ADO, ODBC or OLE DB connection string's parts, keys in lower case with single spaces: braces
    ({ODBC Driver 18 for SQL Server}) and quotes kept as one value. A secret's part is never kept."""
    out: dict[str, str] = {}
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i] in "; \t\r\n":
            i += 1
        equals = text.find("=", i)
        if equals < 0:
            break
        key = norm_key(text[i:equals])
        j = equals + 1
        while j < n and text[j] in " \t":
            j += 1
        if j < n and text[j] in "{\"'":
            close = "}" if text[j] == "{" else text[j]
            end = text.find(close, j + 1)
            end = n if end < 0 else end
            value = text[j + 1 : end]
            semi = text.find(";", end)
            i = n if semi < 0 else semi + 1
        else:
            semi = text.find(";", j)
            end = n if semi < 0 else semi
            value = text[j:end]
            i = end + 1
        if key and not is_secret_key(key) and len(key) <= 40:
            out[key] = value.strip()
    return out


def split_server(server: str) -> tuple[str, int | None, str]:
    """A SQL Server style address in parts: tcp:host,1433 or host\\INSTANCE -> (host, port, instance)."""
    text = re.sub(r"^(?:tcp|np|lpc|admin):", "", server.strip(), flags=re.IGNORECASE)
    port: int | None = None
    if "," in text:
        text, _, after = text.partition(",")
        port = port_of(after)
    instance = ""
    if "\\" in text and not text.startswith("("):
        text, _, instance = text.partition("\\")
        if re.fullmatch(r"[^:]+:\d{1,5}", instance):  # host\INSTANCE:1433 (a JDBC URL's)
            instance, _, after = instance.partition(":")
            port = port_of(after)
    elif re.fullmatch(r"[^:/\\]+:\d{1,5}", text):
        text, _, after = text.partition(":")
        port = port_of(after)
    return text.strip(), port, instance.strip()


def from_pairs(pairs: Mapping[str, str], name: str = "", kind: str = "") -> Found | None:
    """A connection string's parts as a found connection (None when it names no server, file or data
    source)."""
    told = kind or kind_from(pairs.get("driver", "")) or kind_from(pairs.get("provider", ""))
    windows = any(
        pairs.get(k, "").casefold() in TRUE_WORDS for k in ("trusted_connection", "integrated security")
    )
    windows = windows or "integrated" in pairs.get("authentication", "").casefold()
    path = pairs.get("dbq", "")
    server = first_of(pairs, SERVER_KEYS)
    if told in FILE_KINDS and not path:
        path, server = server, ""
    host, port, instance = split_server(server) if server else ("", None, "")
    port = port_of(pairs.get("port")) or port
    database = first_of(pairs, DATABASE_KEYS)
    if told == "oracle" and host and not database:  # EZConnect: host:port/service
        m = re.fullmatch(r"(?://)?([^:/]+)(?::(\d+))?/(.+)", server)
        if m:
            host, port, database = m.group(1), port_of(m.group(2)) or port, m.group(3)
    dsn = pairs.get("dsn", "").strip()
    if not (host or path or dsn):
        return None
    return Found(
        kind=told or ("odbc" if dsn and not host else ""),
        name=name,
        server=host,
        port=port,
        database=database,
        user=first_of(pairs, USER_KEYS),
        windows=windows,
        instance=instance,
        dsn=dsn,
        path=path,
    )


_URL = re.compile(
    r"""^(?P<scheme>[a-z][a-z0-9+._-]*)://(?:(?P<auth>[^@/?#\s]*)@)?(?P<hosts>[^/?#;\s]*)
    (?P<path>/[^?#;\s]*)?(?P<rest>[?;][^\s]*)?$""",
    re.IGNORECASE | re.VERBOSE,
)


def _unquote(text: str) -> str:
    return re.sub(r"%([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), text)


def _params(rest: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in re.split(r"[?;&]", rest or ""):
        key, equals, value = part.partition("=")
        if equals and key.strip() and not is_secret_key(key):
            out[norm_key(_unquote(key))] = _unquote(value).strip()
    return out


def parse_url(text: str, name: str = "") -> Found | None:
    """A JDBC URL (jdbc:postgresql://host:5432/db, jdbc:sqlserver://host;databaseName=db, jdbc:oracle:thin:
    @//host:1521/service, jdbc:sqlite:path) or a database URL (postgresql://user@host/db, mysql+pymysql://...,
    snowflake://account/db) as a found connection; its password, where it has one, is never read."""
    url = text.strip().rstrip(".,)")
    jdbc = url[:5].casefold() == "jdbc:"
    if jdbc:
        url = url[5:]
    head = url.split(":", 1)[0]
    kind = kind_from(head.split("+", 1)[0]) or ("" if head.casefold() in ("http", "https") else "unknown")
    if not kind:
        return None
    if kind in ("sqlite", "duckdb") and not url.casefold().startswith(f"{head}://".casefold()):
        path = url.split(":", 1)[1] if ":" in url else ""
        return Found(kind=kind, name=name, path=path) if path else None
    if kind == "oracle" and "@" in url and "://" not in url.split("@", 1)[0]:
        return _oracle_thin(url, name)
    if jdbc and kind == "sqlserver" and url.casefold().startswith("jtds:"):
        url = url[5:]
    if kind in ("sqlite", "duckdb"):  # sqlite:///C:/data/shop.sqlite
        path = re.sub(r"^[a-z0-9+]+:///?", "", url, flags=re.IGNORECASE)
        return Found(kind=kind, name=name, path=path) if path else None
    m = _URL.match(url)
    if not m:
        return None
    auth, hosts = m.group("auth") or "", m.group("hosts") or ""
    first = hosts.split(",", 1)[0]
    if first.startswith("["):
        host, _, after = first[1:].partition("]")
        port = port_of(after.lstrip(":"))
        instance = ""
    else:
        host, port, instance = split_server(first.replace("\\\\", "\\"))
    params = _params(m.group("rest") or "")
    path_part = (m.group("path") or "").strip("/")
    database = params.get("databasename") or params.get("database") or params.get("db") or ""
    if not database and path_part and kind != "snowflake":
        database = _unquote(path_part.split("/", 1)[0])
    if kind == "snowflake":
        host = re.sub(r"\.snowflakecomputing\.com$", "", host, flags=re.IGNORECASE)
        database = database or _unquote(path_part.split("/", 1)[0])
    user = _unquote(auth.split(":", 1)[0]) if auth else ""
    user = user or params.get("user") or params.get("username") or params.get("uid") or ""
    windows = params.get("integratedsecurity", "").casefold() in TRUE_WORDS
    windows = windows or "integrated" in params.get("authentication", "").casefold()
    if kind == "teradata" and not database:
        for part in re.split(r"[,/]", path_part):
            key, _, value = part.partition("=")
            if key.strip().casefold() == "database":
                database = value.strip()
    if not host:
        return None
    return Found(
        kind=kind,
        name=name,
        server=_unquote(host),
        port=port_of(params.get("port")) or port,
        database=database,
        user=user,
        windows=windows,
        instance=params.get("instancename") or instance,
    )


def _oracle_thin(url: str, name: str) -> Found | None:
    """oracle:thin:user/password@host:1521:SID, @//host:1521/service or @(DESCRIPTION=(...HOST=...))."""
    before, _, after = url.partition("@")
    user = before.split(":")[-1].split("/", 1)[0] if before.count(":") >= 2 else ""
    if after.startswith("("):
        host = re.search(r"HOST\s*=\s*([^)\s]+)", after, re.IGNORECASE)
        port = re.search(r"PORT\s*=\s*(\d+)", after, re.IGNORECASE)
        service = re.search(r"(?:SERVICE_NAME|SID)\s*=\s*([^)\s]+)", after, re.IGNORECASE)
        if not host:
            return None
        return Found(
            kind="oracle",
            name=name,
            server=host.group(1),
            port=port_of(port.group(1)) if port else None,
            database=service.group(1) if service else "",
            user=user,
        )
    m = re.match(r"^/*([^:/]+)(?::(\d+))?[:/]?(.*)$", after)
    if not m:
        return None
    return Found(
        kind="oracle", name=name, server=m.group(1), port=port_of(m.group(2)), database=m.group(3), user=user
    )


def from_object(item: Mapping[str, Any], name: str = "") -> Found | None:
    """An object holding a host, a port and a database (JSON, XML, an INI section) as a found connection;
    its kind from what it says of itself (type, driver, dialect...) or its port. None without all three."""
    flat = {
        re.sub(r"[\s_.-]+", "", str(k)).casefold(): v
        for k, v in item.items()
        if isinstance(k, str)
        and not is_secret_key(k)
        and isinstance(v, str | int)
        and not isinstance(v, bool)
    }
    host = next((flat[k] for k in ("host", "hostname", "server", "servername", "address") if k in flat), "")
    port = port_of(flat.get("port"))
    database = next(
        (flat[k] for k in ("database", "db", "dbname", "databasename", "initialcatalog") if k in flat), ""
    )
    if not isinstance(host, str) or PLACEHOLDER.search(host.strip()) or port is None:
        return None
    if not isinstance(database, str) or not database.strip() or PLACEHOLDER.search(database.strip()):
        return None
    said = " ".join(
        str(flat[k])
        for k in ("type", "driver", "dialect", "provider", "engine", "kind", "vendor", "adapter", "client")
        if k in flat
    )
    user = next((flat[k] for k in ("user", "username", "uid", "userid", "login") if k in flat), "")
    own = next(
        (flat[k] for k in ("name", "title", "label", "connectionname", "profilename") if k in flat), ""
    )
    return Found(
        kind=kind_from(said),
        name=str(own or name),
        server=host.strip(),
        port=port,
        database=database.strip(),
        user=str(user),
    )


# ===== the list: merged, marked, each with what it would become =====


def _norm_server(server: str, instance: str = "") -> str:
    host = server.strip().casefold().rstrip(".")
    if host in (".", "(local)", "127.0.0.1", "::1", "localhost", "(localdb)"):
        host = "localhost"
    return f"{host}\\{instance.casefold()}" if instance else host


def key_of(found: Found) -> str:
    """What one connection is, for telling it from another: its kind's family and its file, data source, or
    server and database (in any case)."""
    family = _FAMILY.get(found.kind, found.kind)
    if found.path:
        path = found.path.strip().replace("\\", "/").casefold()
        return f"{family}|file|{path}"
    if found.kind == "odbc":
        return f"odbc|dsn|{found.dsn.casefold()}"
    return f"{family}|{_norm_server(found.server, found.instance)}|{found.database.strip().casefold()}"


def row_id(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def merge(found: Iterable[Found]) -> list[Found]:
    """The same connection from several tools as one: its sources together, a part one left blank taken from
    another (a user, a port, a name). In the order first found."""
    by: dict[str, Found] = {}
    for f in found:
        k = key_of(f)
        was = by.get(k)
        if was is None:
            by[k] = f
            continue
        sources = was.sources + tuple(s for s in f.sources if s not in was.sources)
        by[k] = replace(
            was,
            name=was.name or f.name,
            user=was.user or f.user,
            port=was.port or f.port,
            dsn=was.dsn or f.dsn,
            windows=was.windows or f.windows,
            sources=sources,
        )
    return list(by.values())


def found_from_settings(template: str | None, settings: Iterable[Mapping[str, Any]]) -> Found | None:
    """A saved connection, as its settings say it (server, port, database, its file or data source), to
    tell a found one it already is."""
    kind = str(template or "")
    if kind not in SUPPORTED:
        return None
    by: dict[str, str] = {}
    for s in settings:
        if not s.get("placeholder"):
            by.setdefault(str(s.get("name")), str(s.get("value") if s.get("value") is not None else ""))
    if kind == "odbc":
        return Found(kind="odbc", dsn=by.get("data source", ""))
    if kind in FILE_KINDS:
        return Found(kind=kind, path=by.get("path", ""))
    server = by.get("server") or by.get("account") or ""
    database = by.get("database") or by.get("catalog") or ""
    if kind == "oracle" and by.get("data source"):
        oracle = from_pairs({"data source": by["data source"]}, kind="oracle")
        server, database = (oracle.server, oracle.database) if oracle else ("", "")
    host, _, instance = split_server(server)
    return Found(kind=kind, server=host, instance=by.get("instance") or instance, database=database)


def name_for(found: Found) -> str:
    """A found connection's name: its tool's, else its database on its server, its data source or file."""
    if found.name:
        return found.name
    if found.path:
        return connection_rules.name_from_path(found.path) or "Database file"
    if found.kind == "odbc" and found.dsn:
        return found.dsn
    if found.database and found.server:
        return f"{found.database} on {found.server}"
    return found.server or found.dsn or "Connection"


_NAME_CHARS = re.compile(r"[^A-Za-z0-9 _.-]+")


def unique_name(base: str, taken: Iterable[str]) -> str:
    """A connection's name from a tool's (pg@localhost -> pg localhost), the next free one ("Sales 2")."""
    plain = " ".join(_NAME_CHARS.sub(" ", base).split()).strip(" .-")
    if not plain:
        plain = "Found connection"
    elif not (plain[0].isalnum() or plain[0] == "_"):
        plain = f"Found {plain}"
    plain = plain[:58].rstrip() or "Found connection"
    used = {t.casefold() for t in taken}
    if plain.casefold() not in used:
        return plain
    n = 2
    while f"{plain} {n}".casefold() in used:
        n += 1
    return f"{plain} {n}"


def unique_variable(connection: str, taken: Iterable[str]) -> str:
    """The password's variable for a connection: Sales DB -> SALES_DB_PASSWORD, or SALES_DB_PASSWORD_2."""
    base = connection_rules.env_name_for(connection, "password")
    used = set(taken)
    if base not in used:
        return base
    n = 2
    while f"{base}_{n}" in used:
        n += 1
    return f"{base}_{n}"


def sign_in(found: Found) -> str:
    """How it signs in, in a word: windows, dsn (its data source's own), file, or password."""
    if found.path:
        return "file"
    if found.kind == "odbc":
        return "dsn"
    return "windows" if found.windows else "password"


@dataclass(frozen=True)
class Row:
    """One row of the list: a found connection (merged) and what the library says of it."""

    id: str
    found: Found
    already: str | None = None  # the library's connection it already is
    supported: bool = True
    notes: list[dict[str, str]] = field(default_factory=list)  # Only works on your machine: ...

    def to_json(self, labels: Mapping[str, str]) -> dict[str, Any]:
        f = self.found
        words = kind_words(f.kind, labels)
        return {
            "id": self.id,
            "name": name_for(f),
            "kind": f.kind,
            "kind_label": words,
            "server": f.server + (f"\\{f.instance}" if f.instance else ""),
            "port": f.port,
            "database": f.database,
            "user": f.user,
            "data_source": f.dsn,
            "path": f.path,
            "sign_in": sign_in(f),
            "from": [s.to_json() for s in f.sources],
            "searched": bool(f.sources) and all(s.searched for s in f.sources),
            "already": self.already,
            "supported": self.supported,
            "why": None if self.supported else f"Swiss Army Bench has no {words} connection yet",
            "local": self.notes,
        }


def rows(found: Iterable[Found], saved: Mapping[str, str]) -> list[Row]:
    """The list: merged, each with its id, whether the library has it (`saved`: key -> its name) and
    whether we have a connection of its kind. Supported first, then by name."""
    out = []
    for f in merge(found):
        k = key_of(f)
        supported = f.kind in SUPPORTED and (f.kind != "access" or bool(f.path))
        out.append(Row(row_id(k), f, saved.get(k), supported))
    out.sort(key=lambda r: (not r.supported, r.already is not None, name_for(r.found).casefold()))
    return out


# ===== import: a row as a library connection made from its starter's code =====


def way_code(found: Found, template: Mapping[str, Any]) -> str:
    """The starter's code for the found connection's sign-in: Windows sign-in where it signed in so, a user
    name and password where the starter has that way, else the starter's own."""
    want = 'sign_in="windows"' if found.windows else 'sign_in="sql_login"'
    way = next((w for w in template.get("sign_ins") or [] if w.get("mark") == want), None)
    return str(way["code"]) if way else str(template["code"])


def _value_for(found: Found, setting: blade_rules.Setting, kind: str) -> Any:
    name = setting.name
    if name == "server":
        if not found.server:
            return None
        has_instance = kind in ("sqlserver", "azuresql")
        return found.server if has_instance or not found.instance else f"{found.server}\\{found.instance}"
    if name == "account":
        return found.server or None
    if name == "port":
        if found.port is None:
            return None
        return str(found.port) if isinstance(setting.value, str) else found.port
    if name in ("database", "catalog"):
        return found.database or None
    if name in ("user", "username"):
        return found.user or None
    if name == "instance":
        return found.instance or None
    if name == "path":
        return found.path or None
    if name == "data source":
        if kind == "odbc":
            return found.dsn or None
        if kind == "oracle" and found.server:
            return f"{found.server}:{found.port or 1521}/{found.database}".rstrip("/")
    return None


_PASSWORD = re.compile(r"""\bsecret\(\s*["']password["']\s*\)""")


def connection_body(
    found: Found, template: Mapping[str, Any], name: str, variable: str | None
) -> tuple[dict[str, Any], str | None]:
    """The Add connection form's body for a found connection: its starter's code (the way it signs in) with
    its server, port, database, user, file or data source filled in, and its password asking for
    `variable` (secret("SALES_DB_PASSWORD"): set on this computer once, never typed here). The body, and the
    variable the code asks for (None: no password)."""
    kind = str(template["id"])
    code = way_code(found, template)
    values: dict[str, Any] = {}
    for setting in blade_rules.detect_settings(code):
        value = _value_for(found, setting, kind)
        if value is None or (
            isinstance(value, str) and ("${" in value or "\n" in value or not value.strip())
        ):
            continue
        if setting.where == "connection string" and isinstance(value, str) and re.search(r"[;\"']", value):
            continue
        values[setting.id] = value
    if values:
        code = blade_rules.apply_settings(code, values)
    used: str | None = None
    if variable and _PASSWORD.search(code):
        code = connection_rules.rename_secret(code, "password", variable)
        used = variable
    tools = ", ".join(dict.fromkeys(s.tool for s in found.sources))
    body = {
        "name": name,
        "kind": template["kind"],
        "template": kind,
        "dialect": template.get("dialect"),
        "variable": template.get("variable"),
        "code": code,
        "catalog": template.get("catalog"),
        "description": f"Found in {tools}" if tools else "Found on this computer",
    }
    return body, used
