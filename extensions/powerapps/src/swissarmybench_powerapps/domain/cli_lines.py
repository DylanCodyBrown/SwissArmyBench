"""Each Power Platform action as the command line it runs, and what each command printed, read.

The Power Apps CLI (`pa`) and the Power Platform CLI (`pac`) do the work; the app writes no project code of
its own (the owner, 2026-11-17: "instead of writing custom code to manage the project we let pac cli do the
work"). Every value a command line carries is checked here: one line of plain text, no secret. A command
line is visible to every process on the computer and lands in shell histories and logs, so a value that
looks like a password, a key or a token is refused before anything runs (the posture: never a secret on a
command line). Sign-in is the CLI's own browser sign-in; its tokens stay in the CLI's own store.

Output is read from JSON where the CLI offers it (`--json`), else from its tables. Pure rules.
"""

from __future__ import annotations

import json
import re
from typing import Any

MAX_VALUE = 500
# A value that is a secret, not a name: a long run of key-like characters, a JWT, a key=value pair of one.
_SECRET_WORDS = re.compile(r"(password|passwd|secret|token|apikey|api_key|client_secret)\s*[=:]", re.I)
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.")
_KEYLIKE = re.compile(r"^[A-Za-z0-9+=_-]{40,}$")  # one long word of key characters (a path's / is not one)
_GUID = re.compile(r"^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$")
_URL_PLAY = re.compile(r"https://[a-z0-9.-]*powerapps\.com/play/[^\s'\"<>]+", re.I)
_URL_LOCAL = re.compile(r"https?://(?:localhost|127\.0\.0\.1):\d+[^\s'\"<>]*")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


class CliError(ValueError):
    """A value a command line may not carry, or an answer that cannot be read."""


def plain(text: str) -> str:
    """A command's output line without its colours."""
    return _ANSI.sub("", text)


def value(name: str, raw: Any, *, required: bool = True, guid: bool = False) -> str:
    """One argument's value, checked: one line, not too long, never a secret."""
    text = "" if raw is None else str(raw).strip()
    if not text:
        if required:
            raise CliError(f"{name} is needed.")
        return ""
    if len(text) > MAX_VALUE or "\n" in text or "\r" in text or "\x00" in text:
        raise CliError(f"{name} is one line of text, at most {MAX_VALUE} characters.")
    if text.startswith("-"):
        raise CliError(f"{name} cannot start with a dash (it would be read as an option).")
    if guid and not _GUID.match(text):
        raise CliError(f"{name} is an id like 00000000-0000-0000-0000-000000000000.")
    if _SECRET_WORDS.search(text) or _JWT.search(text) or (_KEYLIKE.match(text) and not _GUID.match(text)):
        raise CliError(f"{name} looks like a secret: secrets never go on a command line.")
    return text


def check_argv(argv: list[str]) -> list[str]:
    """A whole command line, checked once more just before it runs (every part, the program's too)."""
    for part in argv[1:]:
        if part.startswith("--") or part in ("-p", "-n"):
            continue
        value("A value", part)
    return argv


# ===== the Power Apps CLI (pa) =====


def auth_status() -> list[str]:
    return ["pa", "auth", "status", "--json"]


def auth_login(account: Any = None) -> list[str]:
    argv = ["pa", "auth", "login"]
    if account:
        argv += ["--account", value("The account", account)]
    return argv


def auth_switch(account: Any) -> list[str]:
    return ["pa", "auth", "switch", "--account", value("The account", account)]


def app_init(display_name: Any, environment_id: Any, description: Any = None) -> list[str]:
    argv = [
        "pa",
        "app",
        "init",
        "--display-name",
        value("The app's name", display_name),
        "--environment-id",
        value("The environment", environment_id, guid=True),
    ]
    if description:
        argv += ["--description", value("The description", description)]
    return argv


def add_dataverse_table(table: Any, org_url: Any = None) -> list[str]:
    argv = [
        "pa",
        "app",
        "add",
        "data-source",
        "--connector",
        "dataverse",
        "--table",
        value("The table", table),
    ]
    if org_url:
        url = value("The environment's address", org_url)
        if not url.startswith("https://"):
            raise CliError("The environment's address starts with https://.")
        argv += ["--org-url", url]
    return argv


def add_connector(
    connector: Any,
    connection_id: Any = None,
    connection_ref: Any = None,
    solution_id: Any = None,
    dataset: Any = None,
    tables: Any = None,
    as_kind: Any = None,
) -> list[str]:
    argv = ["pa", "app", "add", "data-source", "--connector", value("The connector", connector)]
    if connection_id and connection_ref:
        raise CliError("A connection or a connection reference, not both.")
    if connection_id:
        argv += ["--connection-id", value("The connection", connection_id)]
    elif connection_ref:
        argv += ["--connection-ref", value("The connection reference", connection_ref)]
        if solution_id:
            argv += ["--solution-id", value("The solution", solution_id)]
    else:
        raise CliError("Choose the connector's connection (pa connection list names them).")
    names = [tables] if isinstance(tables, str) else list(tables or [])
    if as_kind not in (None, "", "table", "action"):
        raise CliError('Add it as "table" or "action".')
    if as_kind == "action" and (dataset or names):
        raise CliError("Actions take no dataset or table.")
    if dataset:
        argv += ["--dataset", value("The dataset", dataset)]
    for name in names:
        argv += ["--table", value("The table", name)]
    if as_kind:
        argv += ["--as", str(as_kind)]
    return argv


def remove_source(connector: Any, name: Any) -> list[str]:
    return [
        "pa",
        "app",
        "remove",
        "data-source",
        "--connector",
        value("The connector", connector),
        "--name",
        value("The data source", name),
        "--force",
    ]


def connector_list(search: Any = None) -> list[str]:
    argv = ["pa", "connector", "list", "--json"]
    if search:
        argv += ["--search", value("The search", search)]
    return argv


def connection_list() -> list[str]:
    return ["pa", "connection", "list", "--json"]


def app_list() -> list[str]:
    return ["pa", "app", "list", "--json"]


def app_push(solution_id: Any = None) -> list[str]:
    argv = ["pa", "app", "push"]
    if solution_id:
        argv += ["--solution-id", value("The solution", solution_id)]
    return argv


def npm_install() -> list[str]:
    return ["npm", "install"]


def npm_build() -> list[str]:
    return ["npm", "run", "build"]


def template(folder_name: str) -> list[str]:
    """Microsoft's current starting point: the Vite template of the PowerAppsCodeApps repository."""
    return ["npx", "--yes", "degit", "github:microsoft/PowerAppsCodeApps/templates/vite", folder_name]


def dev_server(port: int, base: str) -> list[str]:
    """The app's dev server (Vite, with the Power Apps plugin), on 127.0.0.1 only, under `base` so this
    server can pass its pages through without rewriting them (as Streamlit's are)."""
    if not base.startswith("/") or not base.endswith("/"):
        raise CliError("The base path starts and ends with /.")
    return [
        "npm",
        "run",
        "dev",
        "--",
        "--port",
        str(port),
        "--strictPort",
        "--host",
        "127.0.0.1",
        "--base",
        base,
    ]


# ===== the Power Platform CLI (pac) =====


def pac_auth_token() -> list[str]:
    """A Power Platform API token for the selected profile: read in memory only, never shown or logged."""
    return ["pac", "auth", "token"]


def pac_env_list() -> list[str]:
    return ["pac", "env", "list"]


def pac_auth_list() -> list[str]:
    return ["pac", "auth", "list"]


def pac_auth_create(environment: Any = None) -> list[str]:
    argv = ["pac", "auth", "create"]
    if environment:
        argv += ["--environment", value("The environment", environment)]
    return argv


def pac_auth_select(index: Any) -> list[str]:
    try:
        number = int(index)
    except (TypeError, ValueError):
        raise CliError("A profile's index is a whole number (pac auth list shows them).") from None
    if number < 1:
        raise CliError("A profile's index is 1 or more.")
    return ["pac", "auth", "select", "--index", str(number)]


def pac_connector_create(
    definition: str, properties: str, environment: Any = None, update: Any = None
) -> list[str]:
    argv = ["pac", "connector", "update" if update else "create", "--api-definition-file", definition]
    argv += ["--api-properties-file", properties]
    if update:
        argv += ["--connector-id", value("The connector's id", update, guid=True)]
    if environment:
        argv += ["--environment", value("The environment", environment)]
    return argv


# ===== reading what came back =====


def json_of(output: str) -> Any:
    """The JSON a command printed with --json (any lines before it, such as "Connected as ...", skipped)."""
    text = plain(output or "").strip()
    for start in range(len(text)):
        if text[start] in "[{":
            try:
                return json.loads(text[start:])
            except ValueError:
                continue
    raise CliError("The command did not print JSON.")


def accounts(output: str) -> dict[str, Any]:
    """`pa auth status --json`: {signedIn, activeAccount: {username, homeAccountId}, accounts: [...]}"""
    got = json_of(output)
    if not isinstance(got, dict):
        raise CliError("pa auth status did not say who is signed in.")
    listed = [
        {"username": str(a.get("username") or ""), "active": bool(a.get("isActive"))}
        for a in got.get("accounts") or []
        if isinstance(a, dict)
    ]
    active = got.get("activeAccount") if isinstance(got.get("activeAccount"), dict) else None
    return {
        "signed_in": bool(got.get("signedIn")),
        "active": str(active.get("username")) if active else None,
        "accounts": listed,
    }


def connectors(output: str) -> list[dict[str, Any]]:
    """`pa connector list --json`: [{id, name, displayName, description, isTabular}]"""
    got = json_of(output)
    rows = got if isinstance(got, list) else got.get("value", []) if isinstance(got, dict) else []
    found = []
    for r in rows:
        if not isinstance(r, dict) or not r.get("name"):
            continue
        found.append(
            {
                "name": str(r["name"]),
                "id": str(r.get("id") or ""),
                "display_name": str(r.get("displayName") or r["name"]),
                "description": str(r.get("description") or "")[:2000],
                "tabular": bool(r.get("isTabular")),
            }
        )
    return sorted(found, key=lambda c: c["display_name"].casefold())


def connections(output: str) -> list[dict[str, Any]]:
    """`pa connection list --json`: the connections as the service answers them ({name, properties:
    {displayName, apiId, statuses}})."""
    got = json_of(output)
    rows = got if isinstance(got, list) else got.get("value", []) if isinstance(got, dict) else []
    found = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        given = r.get("properties")
        props: dict[str, Any] = given if isinstance(given, dict) else r
        api_id = str(props.get("apiId") or r.get("apiId") or "")
        listed = props.get("statuses")
        statuses: list[Any] = listed if isinstance(listed, list) else []
        status = next((str(s.get("status")) for s in statuses if isinstance(s, dict) and s.get("status")), "")
        found.append(
            {
                "id": str(r.get("name") or r.get("id") or ""),
                "display_name": str(props.get("displayName") or ""),
                "connector": api_id.rstrip("/").split("/")[-1],
                "status": status,
            }
        )
    return found


def code_apps(output: str) -> list[dict[str, Any]]:
    """`pa app list --json`: [{appId, name}]"""
    got = json_of(output)
    rows = got if isinstance(got, list) else []
    return [
        {"id": str(r.get("appId") or ""), "name": str(r.get("name") or "")}
        for r in rows
        if isinstance(r, dict) and r.get("appId")
    ]


# The headings pac's tables use (pac env list, pac auth list): found in the header line by name, longest
# first, since pac separates some headings by a single space ("Index Active Kind      Name Friendly Name").
HEADINGS: tuple[str, ...] = (
    "Environment URL",
    "Environment Url",
    "Environment ID",
    "Environment Id",
    "Friendly Name",
    "Display Name",
    "Unique Name",
    "Index",
    "Active",
    "Kind",
    "Name",
    "Url",
    "User",
    "Cloud",
    "Type",
)


def table(output: str) -> list[dict[str, str]]:
    """A table the CLI printed (pac env list, pac auth list): each column starts where its heading starts
    in the header line (the data is aligned under it). Lines before the header (Connected as ...) skipped."""
    lines = [plain(x).rstrip() for x in (output or "").splitlines()]
    header_at = next(
        (i for i, x in enumerate(lines) if re.search(r"\b(Environment ID|Index)\b", x, re.I)), None
    )
    if header_at is None:
        return []
    header = lines[header_at]
    taken: list[tuple[int, int, str]] = []
    for name in HEADINGS:
        for m in re.finditer(rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])", header):
            if not any(m.start() < end and start < m.end() for start, end, _ in taken):
                taken.append((m.start(), m.end(), name))
    spans = sorted((start, name) for start, _, name in taken)
    rows: list[dict[str, str]] = []
    for line in lines[header_at + 1 :]:
        if not line.strip() or set(line.strip()) <= set("-─ "):
            continue
        row: dict[str, str] = {}
        for i, (start, name) in enumerate(spans):
            end = spans[i + 1][0] if i + 1 < len(spans) else len(line)
            row[name] = line[start:end].strip() if start < len(line) else ""
        rows.append(row)
    return rows


def environments(output: str) -> list[dict[str, Any]]:
    """`pac env list`: each environment's name, id, address and whether it is the active one."""
    found = []
    for row in table(output):
        ident = row.get("Environment ID") or row.get("Environment Id") or ""
        if not _GUID.match(ident):
            continue
        found.append(
            {
                "name": row.get("Display Name", ""),
                "id": ident,
                "url": row.get("Environment URL") or row.get("Environment Url") or "",
                "unique_name": row.get("Unique Name", ""),
                "active": row.get("Active", "").strip() == "*",
            }
        )
    return found


def profiles(output: str) -> list[dict[str, Any]]:
    """`pac auth list`: each sign-in profile (index, active, name, environment's address, user)."""
    found = []
    for row in table(output):
        index = row.get("Index", "").strip("[] ")
        if not index.isdigit():
            continue
        found.append(
            {
                "index": int(index),
                "active": row.get("Active", "").strip() == "*",
                "kind": row.get("Kind", ""),
                "name": row.get("Name", ""),
                "environment": row.get("Friendly Name", ""),
                "url": row.get("Url", ""),
                "user": row.get("User", ""),
            }
        )
    return found


def push_link(output: str) -> str | None:
    """`pa app push`'s answer: "App pushed successfully. You can play your app at <link>"."""
    found = re.search(r"play your app at\s+(https://\S+)", plain(output or ""), re.I)
    if found:
        return found.group(1).rstrip(".")
    play = _URL_PLAY.search(plain(output or ""))
    return play.group(0) if play else None


def dev_urls(line: str) -> dict[str, str]:
    """A dev server's line: its local address (Vite's "Local: http://127.0.0.1:5173/...") or the Local Play
    address the Power Apps plugin prints."""
    text = plain(line)
    found: dict[str, str] = {}
    play = _URL_PLAY.search(text)
    if play:
        found["play"] = play.group(0)
    elif "local" in text.lower():
        local = _URL_LOCAL.search(text)
        if local:
            found["local"] = local.group(0)
    return found


def local_play(environment_id: str, app_url: str) -> str:
    """The Local Play address the Power Apps CLI builds (make.powerapps.com, the app at `app_url`), used
    when the dev server did not print one. It opens in the user's own browser profile, signed in."""
    return (
        f"https://make.powerapps.com/play/e/{_quote(environment_id, '')}/app/local"
        f"?_localAppUrl={_quote(app_url, ':/')}"
    )


def _quote(text: str, safe: str) -> str:
    """Percent-encoding (RFC 3986's unreserved characters and `safe` kept), as urllib's quote."""
    keep = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~" + safe)
    return "".join(c if c in keep else "".join(f"%{b:02X}" for b in c.encode()) for c in text)


_DISABLED = re.compile(r"code apps?.{0,60}(not enabled|disabled|turned off|not allowed)", re.I | re.S)


def plain_error(output: str, environment: str = "") -> str | None:
    """A failure said plainly where it can be recognised: code apps switched off in the environment (an
    administrator's setting), not signed in, a connector the CLI does not support yet."""
    text = plain(output or "")
    if _DISABLED.search(text):
        where = f" in {environment}" if environment else ""
        return (
            f"Code apps are switched off{where}. An administrator turns them on in the Power Platform admin "
            "center: Manage, Environments, the environment, Settings, Product, Features, Power Apps code "
            "apps, Enable code apps."
        )
    if re.search(r"not signed in|run `?pa auth login`?|no active account", text, re.I):
        return "Not signed in: Sign in first (pa auth login opens the browser)."
    if re.search(r"excel ?online", text, re.I) and re.search(r"not (yet )?supported", text, re.I):
        return "Code apps do not support the Excel Online connectors yet."
    return None
