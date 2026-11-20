"""The known tools' files read exactly, and the hint scan (domain/found_connections.py has what a found
connection is and the list; the owner, 2026-11-20: "scan the computer's common apps for connections" / "You
could scan the app directory for hints of what to search for").

  READERS / read     each reader a pure function from one file's text (or a registry key's values, or
                     pgAdmin's rows) to the connections it keeps: ODBC (odbc.ini, .dsn, the registry's
                     ODBC.INI values), SSMS (RegSrvr.xml, UserSettings.xml), DBeaver (data-sources.json; never
                     credentials-config.json), Azure Data Studio and VS Code (settings.json), JetBrains
                     (dataSources.xml, the projects recentProjects.xml names), pgAdmin 4, MySQL Workbench,
                     HeidiSQL, Office (.odc, .udl)
  PLACES             where each tool keeps its file on each system, as data (the adapter resolves the roots)
  hints              connection-shaped strings in one small settings file; SKIP_NAMES and SKIP_PAIRS the
                     folders never looked in, hint_file the files opened

A reader takes only the named parts (never a password key: is_secret_key) and every answer is cleaned (no
Password= or user:password@ text). A file that does not read as its tool's is no connections. Pure: no I/O.
"""

from __future__ import annotations

import configparser
import html
import itertools
import json
import re
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from swissarmybench.domain.found_connections import (
    DATABASE_KEYS,
    FILE_KINDS,
    PLACEHOLDER,
    SERVER_KEYS,
    SUPPORTED,
    TRUE_WORDS,
    USER_KEYS,
    Found,
    Source,
    clean,
    connection_pairs,
    first_of,
    from_object,
    from_pairs,
    is_secret_key,
    kind_from,
    norm_key,
    parse_url,
    port_of,
    split_server,
)

# ===== text formats, read safely =====


def load_jsonc(text: str) -> Any:
    """JSON with comments and trailing commas (VS Code's and Azure Data Studio's settings.json)."""
    out: list[str] = []
    i, n, in_string = 0, len(text), False
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            in_string = c != '"'
            i += 1
            continue
        if c == '"':
            in_string = True
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        elif c in "]}":
            while out and out[-1].isspace():
                out.pop()
            if out and out[-1] == ",":
                out.pop()
        out.append(c)
        i += 1
    return json.loads("".join(out))


def _xml(text: str) -> ET.Element | None:
    """An XML document's root; None for one that declares a DOCTYPE or an entity (never expanded) or does
    not parse."""
    if re.search(r"<!(?:DOCTYPE|ENTITY)", text, re.IGNORECASE):
        return None
    try:
        return ET.fromstring(text.lstrip("\ufeff"))  # noqa: S314 (no DOCTYPE or entity: refused above)
    except ET.ParseError:
        return None


def _local(tag: Any) -> str:
    return str(tag).rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def _child_text(element: ET.Element, name: str) -> str:
    for child in element:
        if _local(child.tag).casefold() == name.casefold():
            return (child.text or "").strip()
    return ""


# ===== the known tools' readers: each one file's text to the connections it keeps =====


def read_dbeaver(text: str) -> list[Found]:
    """DBeaver's data-sources.json (each project's .dbeaver folder). Its credentials-config.json is never
    read: the user names in it sit beside the passwords."""
    data = load_jsonc(text)
    connections = data.get("connections") if isinstance(data, dict) else None
    out: list[Found] = []
    for item in (connections or {}).values() if isinstance(connections, dict) else []:
        if not isinstance(item, dict):
            continue
        config: dict[str, Any] = item["configuration"] if isinstance(item.get("configuration"), dict) else {}
        said = f"{item.get('provider', '')} {item.get('driver', '')}"
        kind = kind_from(said)
        name = str(item.get("name") or "")
        url = str(config.get("url") or "")
        host = str(config.get("host") or "")
        if kind in FILE_KINDS:
            from_url = parse_url(url) if url else None
            path = str(config.get("database") or "") or (from_url.path if from_url else "")
            if path:
                out.append(Found(kind=kind, name=name, path=path))
            continue
        if not host and url:
            found = parse_url(url, name)
            if found:
                out.append(replace(found, kind=kind or found.kind))
            continue
        if not host:
            continue
        auth = str(config.get("auth-model") or "")
        out.append(
            Found(
                kind=kind,
                name=name,
                server=host,
                port=port_of(config.get("port")),
                database=str(config.get("database") or ""),
                user=str(config.get("user") or ""),
                windows=bool(re.search(r"ntlm|windows|integrated|kerberos", auth, re.IGNORECASE)),
            )
        )
    return out


def read_regsrvr(text: str) -> list[Found]:
    """SSMS's registered servers (RegSrvr.xml): each RegisteredServer's name, server and the database and
    sign-in its connection string says (its password, encrypted there, is never read)."""
    root = _xml(text)
    if root is None:
        return []
    out: list[Found] = []
    for element in root.iter():
        if _local(element.tag) != "RegisteredServer" or not _child_text(element, "ServerName"):
            continue
        kind = _child_text(element, "ServerType")
        if kind and kind != "DatabaseEngine":
            continue
        pairs = connection_pairs(_child_text(element, "ConnectionStringWithEncryptedPassword"))
        server, port, instance = split_server(_child_text(element, "ServerName"))
        out.append(
            Found(
                kind="sqlserver",
                name=_child_text(element, "Name"),
                server=server,
                port=port,
                instance=instance,
                database=first_of(pairs, DATABASE_KEYS),
                user=first_of(pairs, USER_KEYS),
                windows=pairs.get("integrated security", "").casefold() in TRUE_WORDS
                or pairs.get("trusted_connection", "").casefold() in TRUE_WORDS,
            )
        )
    return out


def read_ssms_recent(text: str) -> list[Found]:
    """SSMS 18 and later's recent connections (UserSettings.xml): each ServerConnectionItem's instance, its
    sign-in (AuthenticationMethod 0: Windows) and each user it was opened as."""
    root = _xml(text)
    if root is None:
        return []
    out: list[Found] = []
    for item in root.iter():
        if _local(item.tag) != "ServerConnectionItem" or not _child_text(item, "Instance"):
            continue
        server, port, instance = split_server(_child_text(item, "Instance"))
        settings = [e for e in item.iter() if _local(e.tag) == "ServerConnectionSettings"] or [item]
        for each in settings:
            method = _child_text(each, "AuthenticationMethod") or _child_text(item, "AuthenticationMethod")
            pairs = connection_pairs(_child_text(each, "ConnectionStringWithEncryptedPassword"))
            database = _child_text(each, "Database") or first_of(pairs, DATABASE_KEYS)
            database = "" if database.casefold() in ("<default>", "master") else database
            out.append(
                Found(
                    kind="sqlserver",
                    server=server,
                    port=port,
                    instance=instance,
                    database=database,
                    user=_child_text(each, "UserName") or first_of(pairs, USER_KEYS),
                    windows=method == "0",
                )
            )
    return out


def read_editor_settings(text: str) -> list[Found]:
    """A settings.json of Azure Data Studio (datasource.connections) or VS Code (the mssql extension's
    mssql.connections, SQLTools' sqltools.connections)."""
    data = load_jsonc(text) if text.strip() else {}
    if not isinstance(data, dict):
        return []
    out: list[Found] = []
    for item in data.get("datasource.connections") or []:
        if not isinstance(item, dict) or not isinstance(item.get("options"), dict):
            continue
        options = item["options"]
        kind = kind_from(item.get("providerName")) or "sqlserver"
        out.append(_mssql_profile(options, kind, str(options.get("connectionName") or "")))
    for item in data.get("mssql.connections") or []:
        if isinstance(item, dict):
            out.append(_mssql_profile(item, "sqlserver", str(item.get("profileName") or "")))
    for item in data.get("sqltools.connections") or []:
        if not isinstance(item, dict):
            continue
        kind = kind_from(item.get("driver")) or "unknown"
        name = str(item.get("name") or "")
        if item.get("connectString"):
            found = parse_url(str(item["connectString"]), name) or from_pairs(
                connection_pairs(str(item["connectString"])), name, kind
            )
            if found:
                out.append(found)
            continue
        if kind in FILE_KINDS:
            out.append(Found(kind=kind, name=name, path=str(item.get("database") or "")))
            continue
        out.append(
            Found(
                kind=kind,
                name=name,
                server=str(item.get("server") or ""),
                port=port_of(item.get("port")),
                database=str(item.get("database") or ""),
                user=str(item.get("username") or ""),
            )
        )
    return [f for f in out if f.server or f.path]


def _mssql_profile(item: Mapping[str, Any], kind: str, name: str) -> Found:
    if item.get("connectionString"):
        found = from_pairs(connection_pairs(str(item["connectionString"])), name, kind)
        if found:
            return found
    server, port, instance = split_server(str(item.get("server") or ""))
    return Found(
        kind=kind,
        name=name,
        server=server,
        port=port_of(item.get("port")) or port,
        instance=instance,
        database=str(item.get("database") or ""),
        user=str(item.get("user") or ""),
        windows=str(item.get("authenticationType") or "").casefold() == "integrated",
    )


def read_jetbrains(text: str, local: str = "") -> list[Found]:
    """A JetBrains IDE's dataSources.xml (DataGrip, IntelliJ, PyCharm...: the IDE's options folder, or a
    project's .idea): each data source's name, driver and JDBC URL; its user from dataSources.local.xml
    (`local`) by its uuid."""
    root = _xml(text)
    if root is None:
        return []
    users: dict[str, str] = {}
    local_root = _xml(local) if local else None
    for element in local_root.iter() if local_root is not None else []:
        if _local(element.tag) == "data-source" and element.get("uuid"):
            users[str(element.get("uuid"))] = _child_text(element, "user-name")
    out: list[Found] = []
    for element in root.iter():
        if _local(element.tag) != "data-source":
            continue
        name = str(element.get("name") or "")
        url = _child_text(element, "jdbc-url")
        found = parse_url(url, name) if url else None
        if found is None:
            continue
        said = f"{_child_text(element, 'driver-ref')} {_child_text(element, 'jdbc-driver')}"
        user = _child_text(element, "user-name") or users.get(str(element.get("uuid") or ""), "")
        out.append(replace(found, kind=kind_from(said) or found.kind, user=found.user or user))
    return out


def jetbrains_projects(text: str) -> list[str]:
    """The projects a JetBrains IDE's recentProjects.xml names (their .idea/dataSources.xml are read too):
    paths as it writes them ($USER_HOME$ for the home folder)."""
    root = _xml(text)
    if root is None:
        return []
    paths: list[str] = []
    for element in root.iter():
        tag = _local(element.tag)
        value = element.get("key") if tag == "entry" else element.get("value") if tag == "option" else None
        if value and ("/" in value or "\\" in value) and value not in paths:
            paths.append(value)
    return paths[:200]


def read_pgadmin(rows: Iterable[Mapping[str, Any]]) -> list[Found]:
    """pgAdmin 4's servers (its pgadmin4.db's server table: name, host, port, maintenance database, user;
    its password column is never asked for)."""
    out: list[Found] = []
    for row in rows:
        host = str(row.get("host") or row.get("hostaddr") or "")
        if host:
            out.append(
                Found(
                    kind="postgres",
                    name=str(row.get("name") or ""),
                    server=host,
                    port=port_of(row.get("port")),
                    database=str(row.get("maintenance_db") or ""),
                    user=str(row.get("username") or ""),
                )
            )
    return out


def read_mysql_workbench(text: str) -> list[Found]:
    """MySQL Workbench's connections.xml: each db.mgmt.Connection's name, driver and parameters (hostName,
    port, userName, schema; its passwords are in the system's keychain, never here or read)."""
    root = _xml(text)
    if root is None:
        return []
    out: list[Found] = []
    for element in root.iter():
        if element.get("struct-name") != "db.mgmt.Connection" or element.get("type") != "object":
            continue
        name, driver, params = "", "", {}
        for child in element:
            key = child.get("key")
            if key == "name":
                name = (child.text or "").strip()
            elif key == "driver":
                driver = (child.text or "").strip()
            elif key == "parameterValues":
                params = {
                    str(v.get("key")): (v.text or "").strip()
                    for v in child
                    if v.get("key") and not is_secret_key(v.get("key"))
                }
        if not params.get("hostName") and not params.get("socket"):
            continue
        out.append(
            Found(
                kind=kind_from(driver) or "mysql",
                name=name,
                server=params.get("hostName") or "localhost",
                port=port_of(params.get("port")),
                database=params.get("schema", ""),
                user=params.get("userName", ""),
            )
        )
    return out


# HeidiSQL's NetType: how a session reaches its server (its source's TNetType).
_HEIDI_KINDS: dict[int, str] = {
    0: "mysql",
    1: "mysql",
    2: "mysql",
    3: "sqlserver",
    4: "sqlserver",
    5: "sqlserver",
    6: "sqlserver",
    7: "sqlserver",
    8: "postgres",
    9: "postgres",
    10: "sqlite",
    11: "mysql",
    12: "interbase",
    13: "interbase",
    14: "firebird",
    15: "firebird",
    16: "mysql",
    17: "redshift",
    18: "sqlite",
}


def read_heidisql(sessions: Mapping[str, Mapping[str, Any]]) -> list[Found]:
    """HeidiSQL's sessions (its registry key's Servers, or portable_settings.txt read by `heidisql_portable`):
    each one's Host, Port, User, NetType, Databases and WindowsAuth. Its Password is never read."""
    out: list[Found] = []
    for name, values in sessions.items():
        plain = {k.casefold(): v for k, v in values.items() if not is_secret_key(k)}
        host = str(plain.get("host") or "")
        if not host:
            continue
        net = port_of(plain.get("nettype"))
        kind = _HEIDI_KINDS.get(net if net is not None else 0, "unknown")
        databases = str(plain.get("databases") or "").split(";")[0].strip()
        if kind in FILE_KINDS:
            out.append(Found(kind=kind, name=name, path=host.split("|")[0]))
            continue
        server, port, instance = split_server(host)
        out.append(
            Found(
                kind=kind,
                name=name,
                server=server,
                port=port_of(plain.get("port")) or port,
                instance=instance,
                database=databases,
                user=str(plain.get("user") or ""),
                windows=str(plain.get("windowsauth") or "").strip() in ("1", "true", "True"),
            )
        )
    return out


def heidisql_portable(text: str) -> dict[str, dict[str, str]]:
    """HeidiSQL's portable_settings.txt as its sessions: `Servers\\<folder>\\<session>\\Host<|||>1<|||>value`
    lines; a Password line is dropped as it is read."""
    sessions: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        parts = line.split("<|||>")
        if len(parts) < 3 or not parts[0].casefold().startswith("servers\\"):
            continue
        path = parts[0].split("\\")
        if len(path) < 3 or is_secret_key(path[-1]):
            continue
        sessions.setdefault(path[-2], {})[path[-1]] = parts[2].strip()
    return sessions


def read_odbc(
    sources: Mapping[str, Mapping[str, Any]], drivers: Mapping[str, str] | None = None
) -> list[Found]:
    """ODBC data sources: each one's values (the registry's ODBC.INI\\<name>, or an odbc.ini section) with the
    driver its list names. A data source whose driver is one we have a connection for, with its server, is
    that kind (portable: SQL Server on mssql-python); else an ODBC data source (only on this computer)."""
    out: list[Found] = []
    for name, values in sources.items():
        pairs = {norm_key(str(k)): str(v) for k, v in values.items() if not is_secret_key(str(k))}
        said = f"{(drivers or {}).get(name, '')} {pairs.get('driver', '')} {pairs.get('description', '')}"
        kind = kind_from(said)
        pairs.pop("driver", None)
        found = from_pairs(pairs | {"dsn": name}, name, kind)
        if found is None:
            continue
        if (not found.server and not found.path) or kind not in SUPPORTED or kind == "odbc":
            found = replace(found, kind="odbc", server=found.server, path="")
        out.append(replace(found, dsn=name))
    return out


def odbc_ini(text: str) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """An odbc.ini (or a .dsn file, its one [ODBC] section) as its data sources and their drivers' names. A
    secret's line is dropped as it is read."""
    parser = configparser.ConfigParser(interpolation=None, strict=False, delimiters=("=",))
    parser.optionxform = str  # type: ignore[assignment,method-assign]
    try:
        parser.read_string(text)
    except configparser.Error:
        return {}, {}
    drivers: dict[str, str] = {}
    sources: dict[str, dict[str, str]] = {}
    for section in parser.sections():
        values = {k: v for k, v in parser.items(section) if not is_secret_key(k)}
        if section.casefold() == "odbc data sources":
            drivers |= values
        elif section.casefold() != "odbc":
            sources[section] = values
    return sources, drivers


def read_odbc_ini(text: str) -> list[Found]:
    sources, drivers = odbc_ini(text)
    return read_odbc(sources, drivers)


def read_dsn_file(text: str, name: str) -> list[Found]:
    """A file data source (.dsn): its [ODBC] section; named after its file."""
    parser = configparser.ConfigParser(interpolation=None, strict=False, delimiters=("=",))
    try:
        parser.read_string(text)
    except configparser.Error:
        return []
    if not parser.has_section("ODBC"):
        return []
    pairs = {norm_key(k): v for k, v in parser.items("ODBC") if not is_secret_key(k)}
    found = from_pairs(pairs, name, kind_from(pairs.get("driver", "")))
    if found is None:
        return []
    if found.kind not in SUPPORTED or not (found.server or found.path):
        return [replace(found, kind="unknown" if not found.kind else found.kind)]
    return [found]


def read_odc(text: str, name: str) -> list[Found]:
    """An Office data connection (.odc, an HTML file): its odc:ConnectionString."""
    m = re.search(r"<odc:ConnectionString>(.*?)</odc:ConnectionString>", text, re.IGNORECASE | re.DOTALL)
    if not m:
        return []
    found = from_pairs(connection_pairs(html.unescape(m.group(1))), name)
    return [found] if found else []


def read_udl(text: str, name: str) -> list[Found]:
    """A data link (.udl): its OLE DB init string, the line after [oledb] and its comment."""
    for line in text.lstrip("\ufeff").splitlines():
        line = line.strip()
        if line and not line.startswith((";", "[")) and "=" in line:
            found = from_pairs(connection_pairs(line), name)
            return [found] if found else []
    return []


# The readers PLACES names, each from one file's text (and its name, for the readers that name a connection
# after its file). jetbrains_projects and pgAdmin are the adapter's own steps (a list of folders; rows).
READERS: dict[str, Any] = {
    "dbeaver": lambda text, name, local: read_dbeaver(text),
    "regsrvr": lambda text, name, local: read_regsrvr(text),
    "ssms_recent": lambda text, name, local: read_ssms_recent(text),
    "editor_settings": lambda text, name, local: read_editor_settings(text),
    "jetbrains": lambda text, name, local: read_jetbrains(text, local),
    "mysql_workbench": lambda text, name, local: read_mysql_workbench(text),
    "heidisql": lambda text, name, local: read_heidisql(heidisql_portable(text)),
    "odbc_ini": lambda text, name, local: read_odbc_ini(text),
    "dsn": lambda text, name, local: read_dsn_file(text, name),
    "odc": lambda text, name, local: read_odc(text, name),
    "udl": lambda text, name, local: read_udl(text, name),
}


def read(
    reader: str, text: str, name: str = "", source: Source | None = None, local: str = ""
) -> list[Found]:
    """One file's connections by its reader, each cleaned (no password text) and given its source. A file
    that does not read as its tool's is no connections (never an error: it is another tool's business).
    `local`: a JetBrains dataSources.xml's dataSources.local.xml beside it (its user names)."""
    try:
        found: list[Found] = READERS[reader](text, name, local)
    except (ValueError, TypeError, AttributeError, KeyError, RecursionError):
        return []
    return [clean(replace(f, sources=(source,) if source else f.sources)) for f in found]


def stamped(found: Iterable[Found], source: Source) -> list[Found]:
    """Found connections (a registry's, pgAdmin's rows) cleaned and given their source."""
    return [clean(replace(f, sources=(source,))) for f in found]


# ===== where each tool keeps its file (the adapter resolves the roots on this system) =====


@dataclass(frozen=True)
class Place:
    tool: str
    reader: str  # a READERS key, "jetbrains_projects", "pgadmin" or "skip" (a binary file: said, not read)
    systems: frozenset[str]  # windows, mac, linux
    root: str  # ROOTS' key
    pattern: str  # a glob under the root, / between parts


WIN, MAC, LINUX = frozenset({"windows"}), frozenset({"mac"}), frozenset({"linux"})
EVERY = WIN | MAC | LINUX
_EDITORS = (
    ("Azure Data Studio", "azuredatastudio"),
    ("VS Code", "Code"),
    ("VS Code Insiders", "Code - Insiders"),
    ("VSCodium", "VSCodium"),
)
PLACES: tuple[Place, ...] = (
    Place("DBeaver", "dbeaver", WIN, "appdata", "DBeaverData/workspace6/*/.dbeaver/data-sources*.json"),
    Place("DBeaver", "dbeaver", MAC, "library", "DBeaverData/workspace6/*/.dbeaver/data-sources*.json"),
    Place("DBeaver", "dbeaver", LINUX, "share", "DBeaverData/workspace6/*/.dbeaver/data-sources*.json"),
    Place("DBeaver", "dbeaver", EVERY, "home", ".dbeaver4/*/.dbeaver/data-sources*.json"),
    Place("SSMS", "regsrvr", WIN, "appdata", "Microsoft/SQL Server Management Studio/*/RegSrvr.xml"),
    Place("SSMS", "regsrvr", WIN, "appdata", "Microsoft/Microsoft SQL Server/*/Tools/Shell/RegSrvr.xml"),
    Place("SSMS", "ssms_recent", WIN, "appdata", "Microsoft/SQL Server Management Studio/*/UserSettings.xml"),
    Place("SSMS", "skip", WIN, "appdata", "Microsoft/SQL Server Management Studio/*/SqlStudio.bin"),
    Place("SSMS", "skip", WIN, "appdata", "Microsoft/Microsoft SQL Server/*/Tools/Shell/SqlStudio.bin"),
    *(
        Place(tool, "editor_settings", systems, root, f"{folder}/User/settings.json")
        for tool, folder in _EDITORS
        for systems, root in ((WIN, "appdata"), (MAC, "appsupport"), (LINUX, "config"))
    ),
    *(
        Place("JetBrains", reader, systems, root, f"JetBrains/*/options/{file}")
        for reader, file in (("jetbrains", "dataSources.xml"), ("jetbrains_projects", "recentProjects.xml"))
        for systems, root in ((WIN, "appdata"), (MAC, "appsupport"), (LINUX, "config"))
    ),
    Place("pgAdmin 4", "pgadmin", WIN, "appdata", "pgAdmin/pgadmin4.db"),
    Place("pgAdmin 4", "pgadmin", MAC | LINUX, "home", ".pgadmin/pgadmin4.db"),
    Place("MySQL Workbench", "mysql_workbench", WIN, "appdata", "MySQL/Workbench/connections.xml"),
    Place("MySQL Workbench", "mysql_workbench", MAC, "appsupport", "MySQL/Workbench/connections.xml"),
    Place("MySQL Workbench", "mysql_workbench", LINUX, "home", ".mysql/workbench/connections.xml"),
    Place("HeidiSQL", "heidisql", WIN, "programfiles", "HeidiSQL/portable_settings.txt"),
    Place("HeidiSQL", "heidisql", WIN, "localappdata", "Programs/HeidiSQL/portable_settings.txt"),
    Place("ODBC", "odbc_ini", LINUX | MAC, "home", ".odbc.ini"),
    Place("ODBC", "odbc_ini", LINUX, "etc", "odbc.ini"),
    Place("ODBC", "odbc_ini", MAC, "library", "ODBC/odbc.ini"),
    Place("ODBC", "odbc_ini", MAC, "systemlibrary", "ODBC/odbc.ini"),
    Place("ODBC", "dsn", WIN, "commonfiles", "ODBC/Data Sources/*.dsn"),
    Place("Office", "odc", EVERY, "documents", "My Data Sources/*.odc"),
    Place("Office", "udl", EVERY, "documents", "My Data Sources/*.udl"),
)
# Each root in words (a source's where), from the home folder.
ROOT_WORDS: dict[str, str] = {
    "appdata": "AppData\\Roaming",
    "localappdata": "AppData\\Local",
    "programdata": "ProgramData",
    "programfiles": "Program Files",
    "commonfiles": "Program Files\\Common Files",
    "documents": "Documents",
    "home": "~",
    "config": ".config",
    "share": ".local/share",
    "etc": "/etc",
    "appsupport": "Library/Application Support",
    "library": "Library",
    "systemlibrary": "/Library",
}
# The settings roots the hint scan looks through, on each system.
HINT_ROOTS: dict[str, tuple[str, ...]] = {
    "windows": ("appdata", "localappdata", "programdata"),
    "mac": ("appsupport",),
    "linux": ("config", "share"),
}
SKIPPED_BINARY = (
    "SSMS 17 and earlier keep recent connections in SqlStudio.bin, a binary file: it is not read (its "
    "registered servers are)."
)


def where_words(root: str, parts: Sequence[str], system: str) -> str:
    """A folder in words from its root: AppData\\Roaming\\DBeaverData\\workspace6 (Windows' separators on
    Windows)."""
    head = ROOT_WORDS.get(root, root)
    joined = [head, *parts] if head != "~" else ["~", *parts]
    separator = "\\" if system == "windows" and not head.startswith("/") else "/"
    return separator.join(p for p in joined if p)


# ===== the hint scan: what it opens, and what it never looks at =====

HINT_SUFFIXES = frozenset(
    {
        ".json",
        ".xml",
        ".ini",
        ".config",
        ".dsn",
        ".odc",
        ".udl",
        ".properties",
        ".yaml",
        ".yml",
        ".toml",
        ".conf",
    }
)
MAX_FILE_BYTES = 256 * 1024  # a settings file larger than this is not a settings file
MAX_FILES = 4_000  # files opened by one scan, at most
MAX_DEPTH = 4  # folders below a root (AppData\Roaming\<program>\a\b\c)
MAX_SECONDS = 4.0  # the scan stops after this long and says so
MAX_FOUND = 400  # hints kept, at most
# Folders never looked in, by name (in any case): browsers' profiles, password managers, credential and key
# stores, cloud sync caches, caches, the app's own state and library, and package and Git folders.
SKIP_NAMES: frozenset[str] = frozenset(
    {
        "chrome",
        "chromium",
        "google chrome",
        "edge",
        "microsoft edge",
        "mozilla",
        "firefox",
        "bravesoftware",
        "brave-browser",
        "brave",
        "opera",
        "opera software",
        "vivaldi",
        "yandex",
        "safari",
        "arc",
        "thorium",
        "1password",
        "bitwarden",
        "keepass",
        "keepassxc",
        "lastpass",
        "dashlane",
        "enpass",
        "keeper",
        "nordpass",
        "roboform",
        "proton pass",
        "credentials",
        "protect",
        "vault",
        "keychains",
        "keyrings",
        "gnupg",
        "onedrive",
        "dropbox",
        "google drive",
        "googledrivefs",
        "icloud",
        "mobile documents",
        "box",
        "box sync",
        "nextcloud",
        "owncloud",
        "pcloud",
        "mega",
        "megasync",
        "node_modules",
        "cache",
        "caches",
        "code cache",
        "gpucache",
        "cacheddata",
        "temp",
        "tmp",
        "packages",
        "crashpad",
        "logs",
        "swissarmybench",
        "swissarmygrid",
        "swiss army bench",
        "dbeaverdata",
        "jetbrains",
        "pgadmin",
        "azuredatastudio",
        "code",
        "code - insiders",
        "vscodium",
        "power bi desktop",
        "microsoft power bi desktop store app",
        "gcloud",
        "azure",
        "aws",
    }
)
# Folders never looked in by the folder above them too: Microsoft\Windows (the shell's own), Microsoft\SQL
# Server Management Studio (read as SSMS's), Microsoft\Credentials.
SKIP_PAIRS: frozenset[tuple[str, str]] = frozenset(
    {
        ("google", "chrome"),
        ("microsoft", "edge"),
        ("microsoft", "windows"),
        ("microsoft", "credentials"),
        ("microsoft", "protect"),
        ("microsoft", "vault"),
        ("microsoft", "sql server management studio"),
        ("microsoft", "microsoft sql server"),
        ("mysql", "workbench"),
    }
)
# A browser's folder by its words, however its maker spells it (google-chrome, BraveSoftware, Microsoft Edge).
_BROWSER = re.compile(
    r"chrom|firefox|mozilla|brave|opera|vivaldi|yandex|safari|librewolf|waterfox|^(?:microsoft[ -])?edge"
)
_SKIP_FILE = re.compile(
    r"credential|secret|passw|token|cookie|keystore|keychain|vault|\.key$|\.pem$|history", re.IGNORECASE
)


def skip_folder(parts: Sequence[str]) -> bool:
    """A folder the hint scan never looks in, by its parts below a root (any dot folder: .git, .ssh)."""
    low = [p.casefold() for p in parts]
    if any(p.startswith(".") or p in SKIP_NAMES or _BROWSER.search(p) for p in low):
        return True
    return any((a, b) in SKIP_PAIRS for a, b in itertools.pairwise(low))


def hint_file(name: str, size: int) -> bool:
    """A file the hint scan opens: a small settings file by its suffix, never one named for a secret."""
    dot = name.rfind(".")
    suffix = name[dot:].casefold() if dot >= 0 else ""
    return suffix in HINT_SUFFIXES and 0 < size <= MAX_FILE_BYTES and not _SKIP_FILE.search(name)


# ===== the hint scan: connection-shaped strings in one file's text =====

_URL_HINT = re.compile(
    r"""(?ix)
    jdbc:[a-z0-9]+(?::[a-z0-9]+)*:[^\s"'<>`]+
    | \b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|mssql|sqlserver|oracle|redshift|snowflake
         |clickhouse|cockroachdb|trino|presto)(?:\+[a-z0-9_]+)?://[^\s"'<>`]+
    """
)
_SNOWFLAKE = re.compile(r"https?://([a-z0-9_-]+(?:\.[a-z0-9_-]+)*)\.snowflakecomputing\.com", re.IGNORECASE)
_PAIR_START = re.compile(r"(?i)\b(?:server|data source|driver)\s*=")


def hints(text: str, file_name: str) -> list[Found]:
    """The connection-shaped strings in one file's text: JDBC and database URLs, Snowflake account
    addresses, ADO/ODBC strings (Server= or Data Source= with Database= or Initial Catalog=, or a Driver=
    with a server) and, in JSON, XML, TOML and INI files, objects with a host, a port and a database. None
    of them holds a password once read (clean)."""
    out: list[Found] = []
    for m in _URL_HINT.finditer(text):
        found = parse_url(html.unescape(m.group(0)).replace("\\\\", "\\"))
        if found and (found.path or not PLACEHOLDER.search(found.server)):
            out.append(found)
    for m in _SNOWFLAKE.finditer(text):
        if not PLACEHOLDER.search(m.group(1)):
            out.append(Found(kind="snowflake", server=m.group(1)))
    out += _string_hints(text)
    suffix = file_name[file_name.rfind(".") :].casefold() if "." in file_name else ""
    try:
        out += _object_hints(text, suffix)
    except (ValueError, TypeError, RecursionError, configparser.Error, tomllib.TOMLDecodeError):
        pass
    return [clean(f) for f in out]


def _string_hints(text: str) -> list[Found]:
    out: list[Found] = []
    seen: set[str] = set()
    for m in _PAIR_START.finditer(text):
        start = max(text.rfind(c, 0, m.start()) for c in "\"'>\n`")
        tail = text[m.start() :]
        stops = [i for i in (tail.find(c) for c in "\"'<\n`") if i >= 0]
        segment = text[start + 1 : m.start() + (min(stops) if stops else len(tail))]
        segment = html.unescape(segment).replace("\\\\", "\\")
        if segment in seen or segment.count("=") < 2:
            continue
        seen.add(segment)
        pairs = connection_pairs(segment)
        server = first_of(pairs, SERVER_KEYS)
        database = first_of(pairs, DATABASE_KEYS)
        if not server or PLACEHOLDER.search(server.split(",")[0].split("\\")[0].strip()):
            continue
        if not database and not pairs.get("driver") and not pairs.get("provider"):
            continue
        found = from_pairs(pairs)
        if found and not found.kind and found.port in (None, 1433):
            # Server= and Database= with no driver or provider named: .NET's SqlClient's, SQL Server's.
            found = replace(found, kind="sqlserver")
        if found:
            out.append(found)
    return out


def _walk_objects(value: Any, depth: int = 0) -> Iterable[Mapping[str, Any]]:
    if depth > 12:
        return
    if isinstance(value, dict):
        yield value
        for v in value.values():
            yield from _walk_objects(v, depth + 1)
    elif isinstance(value, list):
        for v in value[:500]:
            yield from _walk_objects(v, depth + 1)


def _object_hints(text: str, suffix: str) -> list[Found]:
    objects: list[Mapping[str, Any]] = []
    if suffix == ".json":
        objects = list(_walk_objects(load_jsonc(text)))
    elif suffix == ".toml":
        objects = list(_walk_objects(tomllib.loads(text)))
    elif suffix in (".xml", ".config"):
        root = _xml(text)
        for element in root.iter() if root is not None else []:
            item: dict[str, Any] = dict(element.attrib)
            item |= {_local(c.tag): (c.text or "").strip() for c in element if not len(c)}
            objects.append(item)
    elif suffix in (".ini", ".conf", ".properties"):
        body = text if suffix != ".properties" else "[properties]\n" + text
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.read_string(body)
        for section in parser.sections():
            pairs = {k.rsplit(".", 1)[-1]: v for k, v in parser.items(section)}
            objects.append(pairs | {"name": section} if section != "properties" else pairs)
    out = []
    for each in objects:
        found = from_object(each)
        if found:
            out.append(found)
    return out
