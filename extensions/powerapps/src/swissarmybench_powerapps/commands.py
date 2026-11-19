"""The Power Apps extension's agent commands (the golden rule: every action on its page is one of these).
The base's registry (swissarmybench/cli/commands.py) takes them when the extension is on, so each is
an MCP tool too. Push, a custom connector and installing a tool wait for the user's Allow. Standard
library only.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from swissarmybench.cli import api
from swissarmybench.cli.commands import Command, Registrar, opt, req

COMMANDS: dict[str, Command] = {}


command = Registrar(COMMANDS)


LONG = 960.0  # an install or a push can take minutes


@command(
    "powerapps_state",
    "The Code App page's picture: tools, account, environments, the open code app, Run live, recent runs",
)
def powerapps_state(a: dict[str, Any]) -> Any:
    return api.call("GET", "/powerapps")


@command(
    "powerapps_tools",
    "Node.js, npm, pa, pac, Deno: found, versions, install commands; `install` installs one (Allow)",
    opt("refresh", "true: look again.", "bool"),
    opt("install", "A tool's id to install (node, pa, pac, dotnet, deno)."),
)
def powerapps_tools(a: dict[str, Any]) -> Any:
    if a.get("install"):
        return api.call("POST", "/powerapps/tools/install", {"tool": a["install"]}, timeout=LONG)
    return api.call("GET", "/powerapps/tools", params={"refresh": "1" if a.get("refresh") else None})


@command(
    "powerapps_auth",
    "Who pa is signed in as; `sign_in` opens the browser sign-in; `switch` makes an account active",
    opt("sign_in", "true: pa auth login.", "bool"),
    opt("account", "The account to prefill (sign_in) or to make active (switch)."),
    opt("switch", "true: pa auth switch to `account`.", "bool"),
)
def powerapps_auth(a: dict[str, Any]) -> Any:
    if a.get("sign_in"):
        return api.call("POST", "/powerapps/account/sign-in", {"account": a.get("account")}, timeout=LONG)
    if a.get("switch"):
        return api.call("POST", "/powerapps/account/switch", {"account": a.get("account")})
    return api.call("GET", "/powerapps/account")


@command(
    "powerapps_environments", "The environments this sign-in reaches (pac env list), the code app's marked"
)
def powerapps_environments(a: dict[str, Any]) -> Any:
    return api.call("GET", "/powerapps/environments")


@command(
    "powerapps_profiles",
    "pac's sign-in profiles; `create` signs in (the browser) for an environment; `select` makes one active",
    opt("create", "true: pac auth create.", "bool"),
    opt("environment", "create's environment (id, address or name)."),
    opt("select", "A profile's index to make active.", "int"),
)
def powerapps_profiles(a: dict[str, Any]) -> Any:
    if a.get("create"):
        return api.call("POST", "/powerapps/profiles", {"environment": a.get("environment")}, timeout=LONG)
    if a.get("select") is not None:
        return api.call("PUT", "/powerapps/profiles", {"index": a["select"]})
    return api.call("GET", "/powerapps/profiles")


@command(
    "powerapps_project",
    "The open code app: its name, environment, data sources, generated models and services",
)
def powerapps_project(a: dict[str, Any]) -> Any:
    return api.call("GET", "/powerapps/project")


@command(
    "powerapps_new",
    "New code app: Microsoft's template into parent/<name>, npm install, pa app init; then it is open",
    req("name", "The app's display name."),
    req("environment_id", "The environment's id (powerapps_environments)."),
    req("parent", "The folder it goes in."),
    opt("description", "The app's description."),
)
def powerapps_new(a: dict[str, Any]) -> Any:
    body = {k: a.get(k) for k in ("name", "environment_id", "parent", "description")}
    return api.call("POST", "/powerapps/project/new", body, timeout=LONG)


@command(
    "powerapps_open",
    "Open a code app folder (it has power.config.json); `close` closes the open one",
    opt("folder", "The code app's folder."),
    opt("close", "true: close the open code app.", "bool"),
)
def powerapps_open(a: dict[str, Any]) -> Any:
    if a.get("close"):
        return api.call("POST", "/powerapps/project/close", {})
    return api.call("POST", "/powerapps/project/open", {"folder": a.get("folder")})


@command(
    "powerapps_files",
    "The code app's files a person edits (.ts and .tsx under src/; `all` lists every file); `path` reads "
    "one (a hidden one too); `path` and `text` save it",
    opt("path", "A file's path in the app (src/App.tsx)."),
    opt("text", "The file's new text (saves it)."),
    opt("all", "true: every file (configs, generated, .power/).", "bool"),
)
def powerapps_files(a: dict[str, Any]) -> Any:
    if a.get("path") and a.get("text") is not None:
        return api.call("PUT", "/powerapps/project/file", {"path": a["path"], "text": a["text"]})
    if a.get("path"):
        return api.call("GET", "/powerapps/project/file", params={"path": a["path"]})
    return api.call("GET", "/powerapps/project/files", params={"all": "1" if a.get("all") else None})


@command(
    "powerapps_pages",
    "The app's pages (each a folder under src/pages that owns its components, hooks, state and types); "
    "`name` makes a New page and lists it in src/pages.ts",
    opt("name", "New page: its name (Accounts, Open orders)."),
    opt("source", "New page: a data source whose generated service its hook reads."),
)
def powerapps_pages(a: dict[str, Any]) -> Any:
    if a.get("name"):
        return api.call("POST", "/powerapps/pages", {"name": a["name"], "source": a.get("source")})
    return api.call("GET", "/powerapps/pages")


@command(
    "powerapps_scaffold",
    "The starter files where none is: src/shared (Page, useLoad, DataTable, FormField, the app's context), "
    "the Accounts page, src/pages.ts and App.tsx's page switcher",
)
def powerapps_scaffold(a: dict[str, Any]) -> Any:
    return api.call("POST", "/powerapps/project/scaffold", {})


@command(
    "powerapps_lint",
    "The pages rule: an import from another page (move the piece to src/shared/); one file as sent, or all",
    opt("path", "A file's path (with `text`)."),
    opt("text", "The file's text as it stands."),
)
def powerapps_lint(a: dict[str, Any]) -> Any:
    return api.call("POST", "/powerapps/project/lint", {"path": a.get("path"), "text": a.get("text")})


@command(
    "powerapps_add_source",
    "Add a data source (pa app add data-source): a Dataverse table, or a connector with its connection",
    opt("table", "Dataverse: the table's logical name; a connector: its table."),
    opt("connector", "A connector's id (shared_office365users); none: Dataverse."),
    opt("connection_id", "The connector's connection (powerapps_connections)."),
    opt("dataset", "A tabular connector's dataset (a site, a server,database)."),
    opt("as", "table or action, for a connector that has both."),
    opt("org_url", "Dataverse: the environment's https address."),
)
def powerapps_add_source(a: dict[str, Any]) -> Any:
    connector = a.get("connector")
    body: dict[str, Any] = {"kind": "connector" if connector and connector != "dataverse" else "dataverse"}
    body |= {k: a.get(k) for k in ("table", "connector", "connection_id", "dataset", "as", "org_url")}
    return api.call("POST", "/powerapps/sources", body, timeout=LONG)


@command(
    "powerapps_remove_source",
    "Remove a data source (pa app remove data-source)",
    req("name", "The data source's name (powerapps_project lists them)."),
)
def powerapps_remove_source(a: dict[str, Any]) -> Any:
    return api.call("POST", "/powerapps/sources/remove", {"name": a["name"]})


@command(
    "powerapps_connectors",
    "The environment's connectors (pa connector list), searched; in_app marks the app's",
    opt("q", "Words to search for."),
    opt("refresh", "true: ask pa again.", "bool"),
)
def powerapps_connectors(a: dict[str, Any]) -> Any:
    params = {"q": a.get("q"), "refresh": "1" if a.get("refresh") else None}
    return api.call("GET", "/powerapps/connectors", params=params)


@command(
    "powerapps_connector",
    "One connector's operations, inputs and outputs (the APIs explorer's model; read-only)",
    req("name", "The connector's id (shared_office365users)."),
)
def powerapps_connector(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/powerapps/connectors/{quote(str(a['name']), safe='')}")


@command(
    "powerapps_connections",
    "The environment's connections (pa connection list), for Add to app",
    opt("connector", "Only this connector's."),
)
def powerapps_connections(a: dict[str, Any]) -> Any:
    return api.call("GET", "/powerapps/connections", params={"connector": a.get("connector")})


@command(
    "powerapps_run_live",
    "Run live: the app's dev server, shown in the Code App page's pane; its Local Play link; `stop` stops it",
    opt("stop", "true: stop it.", "bool"),
    opt("state", "true: only say whether it runs.", "bool"),
)
def powerapps_run_live(a: dict[str, Any]) -> Any:
    if a.get("state"):
        return api.call("GET", "/powerapps/live")
    if a.get("stop"):
        return api.call("DELETE", "/powerapps/live")
    return api.call("POST", "/powerapps/live", {})


@command(
    "powerapps_push",
    "Push: npm run build, then pa app push, a new version in the environment (waits for the user's Allow)",
    opt("dry_run", "true: say what would run; nothing runs.", "bool"),
    opt("solution_id", "The solution to add the app to."),
)
def powerapps_push(a: dict[str, Any]) -> Any:
    body = {"dry_run": bool(a.get("dry_run")), "solution_id": a.get("solution_id")}
    return api.call("POST", "/powerapps/push", body, timeout=LONG)


@command(
    "powerapps_versions",
    "The environment's code apps (pa app list), this one marked, and this session's pushes",
)
def powerapps_versions(a: dict[str, Any]) -> Any:
    return api.call("GET", "/powerapps/versions")


@command(
    "powerapps_custom_connector",
    "A custom connector from a library API: dry run (the default) shows its two files; dry_run false runs "
    "pac connector create (waits for Allow)",
    req("api", "The API's name (apis_list)."),
    opt("dry_run", "false: write the files and make the connector.", "bool"),
    opt("connector_id", "Update this custom connector instead."),
    opt("folder", "Where the two files go (default: the app's connectors/<api>/)."),
)
def powerapps_custom_connector(a: dict[str, Any]) -> Any:
    body = {
        "api": a["api"],
        "dry_run": a.get("dry_run") is not False,
        "connector_id": a.get("connector_id"),
        "folder": a.get("folder"),
    }
    return api.call("POST", "/powerapps/custom-connector", body, timeout=LONG)


@command(
    "powerapps_runs",
    "This session's pa, pac and npm runs (their words, exit codes, output); `run` gives one's whole output",
    opt("run", "A run's id."),
)
def powerapps_runs(a: dict[str, Any]) -> Any:
    if a.get("run"):
        return api.call("GET", f"/powerapps/runs/{quote(str(a['run']), safe='')}")
    return api.call("GET", "/powerapps/runs")


# ===== the data notebook (phase 2): TypeScript and SQL cells on Deno's kernel, data.ts, TSX =====

RUN = 600.0  # a cell can run for minutes; the first start fetches DuckDB's Node package


@command(
    "powerapps_notebook",
    "The data notebook: its kernels and Deno; `open` makes the code app's data.ipynb (SQL and TypeScript "
    "cells on one DuckDB) and gives its path; `interrupt`, `restart` or `stop` its kernel",
    opt("open", "true: the code app's data notebook (made the first time).", "bool"),
    opt("interrupt", "true: interrupt the running cell.", "bool"),
    opt("restart", "true: a fresh kernel (every variable gone).", "bool"),
    opt("stop", "true: end the kernel.", "bool"),
    opt("path", "The notebook (default: the code app's data.ipynb)."),
)
def powerapps_notebook(a: dict[str, Any]) -> Any:
    body = {"path": a.get("path")}
    for verb in ("open", "interrupt", "restart", "stop"):
        if a.get(verb):
            return api.call("POST", f"/powerapps/notebook/{verb}", body, timeout=RUN)
    return api.call("GET", "/powerapps/notebook")


@command(
    "powerapps_ts_run",
    "Run a TypeScript or SQL cell in the data notebook's Deno kernel (one DuckDB; the open tables are views "
    "by name; `sab.sql`, `sab.table`); its outputs (a table: columns, first rows, total, id)",
    req("code", "The cell's TypeScript, or its SQL (kind sql)."),
    opt("kind", "typescript (the default) or sql."),
    opt("path", "The notebook (default: the code app's data.ipynb)."),
    opt("cell", "The cell's number (for its error's place).", "int"),
)
def powerapps_ts_run(a: dict[str, Any]) -> Any:
    body = {
        "code": a["code"],
        "kind": a.get("kind") or "typescript",
        "path": a.get("path"),
        "cell": a.get("cell"),
    }
    return api.call("POST", "/powerapps/notebook/run", body, timeout=RUN)


@command(
    "powerapps_ts_grid",
    "Open a TypeScript or SQL cell's table result as a grid (every row), by its id (r and a number)",
    req("id", "The result's id (its output says it)."),
    opt("name", "The grid's name."),
    opt("path", "The notebook (default: the code app's data.ipynb)."),
)
def powerapps_ts_grid(a: dict[str, Any]) -> Any:
    body = {"id": a["id"], "name": a.get("name"), "path": a.get("path")}
    return api.call("POST", "/powerapps/notebook/grid", body, timeout=RUN)


@command(
    "powerapps_data_ts",
    "data.ts from the data notebook's TypeScript cells (exported, typed results); `use_in_app` writes it "
    "into the code app's src/ (Use in app)",
    opt("use_in_app", "true: write src/data.ts.", "bool"),
    opt("path", "The notebook (default: the code app's data.ipynb, as saved)."),
)
def powerapps_data_ts(a: dict[str, Any]) -> Any:
    route = "use-in-app" if a.get("use_in_app") else "data-ts"
    return api.call("POST", f"/powerapps/notebook/{route}", {"path": a.get("path")}, timeout=RUN)


@command(
    "powerapps_tsx_preview",
    "Draw a TSX cell (its default export, the code app's own React; `// props: {...}` on its first line "
    "worked out in the notebook's kernel): the page, its frame policy and the props' names",
    req("source", "The TSX cell's code."),
    opt("path", "The notebook (default: the code app's data.ipynb)."),
    opt("cell", "The cell's number.", "int"),
)
def powerapps_tsx_preview(a: dict[str, Any]) -> Any:
    body = {"source": a["source"], "path": a.get("path"), "cell": a.get("cell")}
    return api.call("POST", "/powerapps/notebook/preview", body, timeout=RUN)


@command(
    "powerapps_dataverse_grid",
    "Open one of the code app's Dataverse sources as a grid through the library's Dataverse connection for "
    "its environment; with none, which connection to add",
    req("source", "The source's name (powerapps_project lists them)."),
)
def powerapps_dataverse_grid(a: dict[str, Any]) -> Any:
    return api.call("POST", "/powerapps/dataverse/grid", {"source": a["source"]}, timeout=RUN)
