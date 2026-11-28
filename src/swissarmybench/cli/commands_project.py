"""The agent's project_* commands: projects: a folder (its files, and .sab/: tables, steps, Analyze, relationships).

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from swissarmybench.cli import api
from swissarmybench.cli.api import CommandError
from swissarmybench.cli.command_kit import _q, command, opt, req


@command(
    "project_tree",
    "The Notebooks or Scripts page's explorer tree. "
    "The Notebooks or Scripts page's explorer: the open project's notebooks, or every .py by module with "
    "its outline (classes, functions, methods, constants), made files marked",
    opt("page", "scripts (default) or notebooks."),
)
def project_tree(a: dict[str, Any]) -> Any:
    if (a.get("page") or "scripts") == "scripts":
        return api.call("GET", "/scripts/tree")  # the project's code, the library's, what the app generates
    return api.call("GET", f"/project/tree?{urlencode({'page': a['page']})}")


@command(
    "project_new",
    "A new project folder, scaffolded and opened. "
    "A new project folder, scaffolded and opened (the open tables go into data.ipynb): name (in the projects "
    "folder, or folder), or path (a new or empty folder)",
    opt("name", "Its name (its folder's)."),
    opt("folder", "Where its folder goes (default: the projects folder)."),
    opt("path", "The project's own folder: new or empty."),
    opt("where", "local (default) or shared: which projects folder its folder goes in."),
    opt("type", "bi (default) or an extension's (project_types lists them)."),
    opt("app", "true: a Streamlit app's canvas too.", "bool"),
    opt("notebooks", 'Notebooks to make: ["analysis"].', "json"),
    opt("autosave", "false: save only on project_save.", "bool"),
    opt("discard", "true: let the open project's unsaved changes go.", "bool"),
)
def project_new(a: dict[str, Any]) -> Any:
    keys = ("name", "folder", "where", "path", "type", "app", "notebooks", "autosave", "discard")
    return api.call("POST", "/project/new", {k: a[k] for k in keys if a.get(k) is not None})


@command("project_autosave", "Autosave on or off for the open project", req("on", "true or false.", "bool"))
def project_autosave(a: dict[str, Any]) -> Any:
    return api.call("POST", "/project/autosave", {"on": a["on"]})


@command(
    "project_private",
    "Mark the open project private (on Allow). "
    "Mark the open project private: nothing of it is sent out (the user's Allow)",
    req("on", "true or false.", "bool"),
)
def project_private(a: dict[str, Any]) -> Any:
    return api.call("POST", "/project/private", {"on": a["on"]})


@command(
    "project_summary",
    "Home's summary of the open project. Its name, type, Local or Shared, folder, unsaved, Autosave, "
    "its Python, tables, documents, the connections it uses, the Session's last entries and its "
    "deliverable",
)
def project_summary(a: dict[str, Any]) -> Any:
    return api.call("GET", "/project/summary")


@command(
    "project_documents",
    "The open project's notebooks, scripts and apps",
    opt("kind", "notebook, script or app."),
)
def project_documents(a: dict[str, Any]) -> Any:
    kind = a.get("kind")
    return api.call("GET", "/project/documents" + (f"?kind={_q(kind)}" if kind else ""))


@command(
    "project_scaffold",
    "The open project's made files: status, refresh, take. "
    "The open project's made files (adapter.py, connections.py, README.md's Variables, data.py's structures, "
    "the sandbox mirror): status, refresh, or take the new one over a hand edit",
    req("action", "status, refresh or take."),
    opt("file", "take: the made file (connections.py, adapter.py, ...)."),
)
def project_scaffold(a: dict[str, Any]) -> Any:
    action = str(a["action"])
    if action == "status":
        return api.call("GET", "/project/scaffold")
    if action == "refresh":
        return api.call("POST", "/project/scaffold", {})
    if action == "take":
        return api.call("POST", "/project/scaffold/take", {"file": a.get("file")})
    raise CommandError("action is status, refresh or take.")


@command(
    "project_outline",
    "The open project's outline, ARCHITECTURE.md. "
    "The open project's outline as markdown (ARCHITECTURE.md: sources, tables, steps, lineage, "
    "deliverables, running it, open issues). write: one edited by hand is kept and said (edited) until replace",
    opt("write", "true: write ARCHITECTURE.md at the project's top, as Export outline does.", "bool"),
    opt("replace", "With write: take the new outline over one edited by hand.", "bool"),
)
def project_outline(a: dict[str, Any]) -> Any:
    if a.get("write"):
        done = api.call("POST", "/project/outline", {"replace": bool(a.get("replace"))})
        said = {k: done[k] for k in ("file", "path", "written", "edited", "said") if k in done}
        return said | {"text": done["text"]}
    payload, _ = api.fetch_bytes("GET", "/project/outline")
    return payload.decode("utf-8")


@command(
    "project_import",
    "Copy documents, connections or blades into the project. "
    "Copy into the open project from another project folder, a loose file or this computer's saved "
    'connections and blades ("computer"); list: what it offers',
    req("source", 'A project folder, a notebook, script or app, or "computer".'),
    opt("documents", "Paths there to copy.", "json"),
    opt("connections", "Connection names to copy.", "json"),
    opt("blades", "Blade names to copy.", "json"),
    opt("list", "true: only list what it offers.", "bool"),
)
def project_import(a: dict[str, Any]) -> Any:
    if a.get("list"):
        return api.call("POST", "/project/import/sources", {"from": a["source"]})
    keys = ("documents", "connections", "blades")
    body = {"from": a["source"]} | {k: a[k] for k in keys if a.get(k) is not None}
    return api.call("POST", "/project/import", body)


@command(
    "project_open",
    "Open a project's folder. Tables read again with their steps, Analyze, relationships. Refused "
    "while unsaved changes are open, unless discard; a plain folder answers not_a_project (make: "
    "true)",
    req("path", "The project's folder."),
    opt("make", "true: make a plain folder a project around its files.", "bool"),
    opt("discard", "true: let the open project's unsaved changes go.", "bool"),
)
def project_open(a: dict[str, Any]) -> Any:
    body = {"path": a["path"], "discard": a.get("discard") is True, "make": a.get("make") is True}
    return api.call("POST", "/project/open", body)


@command(
    "project_save",
    "Write the open project's .sab/. Tables, steps, Analyze, relationships. Rows are kept only for "
    "tables ticked in keep_rows: then it waits for the user's Allow",
    opt("keep_rows", '{"pasted_1": true}: keep its rows in .sab/data/.', "json"),
    opt("path", "No project open: a new or empty folder to make the open work one."),
)
def project_save(a: dict[str, Any]) -> Any:
    return api.call("POST", "/project/save", {k: a[k] for k in ("keep_rows", "path") if a.get(k) is not None})


@command(
    "project_copy",
    "Copy the project to a new folder (rows: on Allow). "
    "Copy project to a new or empty folder (saved first); data: its kept rows too (waits for Allow)",
    req("path", "The new folder."),
    opt("data", "true: copy .sab/data/ too.", "bool"),
    opt("folder", "A project that is not open (default: the open one)."),
)
def project_copy(a: dict[str, Any]) -> Any:
    return api.call(
        "POST", "/project/copy", {k: a[k] for k in ("path", "data", "folder") if a.get(k) is not None}
    )


@command(
    "project_recent",
    "The open project and the recent ones. "
    "The open project (unsaved changes, tables that need a fix) and the recent ones",
    opt("remove", "A recent project's path to take off the list."),
)
def project_recent(a: dict[str, Any]) -> Any:
    if a.get("remove"):
        api.call("POST", "/project/recent/remove", {"path": a["remove"]})
    return api.call("GET", "/project")


@command(
    "project_close",
    "Close the project and its tables. "
    "Close the project: its tables, Analyze and relationships. Refused with unsaved changes, unless discard",
    opt("discard", "true: let its unsaved changes go.", "bool"),
)
def project_close(a: dict[str, Any]) -> Any:
    return api.call("POST", "/project/close", {"discard": a.get("discard") is True})


@command(
    "project_table_fix",
    "Fix a table that did not come back on open. "
    "A table that did not come back on open: path (its file now), remove, or neither (try again)",
    req("table", "The table's name."),
    opt("path", "Where its file is now."),
    opt("remove", "true: take it out of the project.", "bool"),
)
def project_table_fix(a: dict[str, Any]) -> Any:
    return api.call(
        "POST", "/project/fix", {k: a[k] for k in ("table", "path", "remove") if a.get(k) is not None}
    )


@command(
    "project_rename",
    "Rename a project (its folder; not the open one)",
    req("path", "The project's folder."),
    req("name", "The new name."),
)
def project_rename(a: dict[str, Any]) -> Any:
    return api.call("POST", "/projects/rename", {"path": a["path"], "name": a["name"]})


@command(
    "project_remove_from_list",
    "Take a project off the Project Explorer. "
    "Take a project off the Project Explorer (no file touched); to: where a moved one is now",
    req("path", "The project's folder."),
    opt("to", "Locate: its folder now (it stays listed there)."),
)
def project_remove_from_list(a: dict[str, Any]) -> Any:
    if a.get("to"):
        return api.call("POST", "/projects/locate", {"path": a["path"], "to": a["to"]})
    return api.call("POST", "/projects/remove", {"path": a["path"]})


@command(
    "project_share",
    "Share a local project (no rows; on Allow). "
    "Share a local project: copied into the shared projects folder (no rows), then opened; waits for Allow",
    req("path", "The local project's folder."),
    opt("name", "Its name there (when its own is taken)."),
)
def project_share(a: dict[str, Any]) -> Any:
    return api.call("POST", "/projects/share", {k: a[k] for k in ("path", "name") if a.get(k)}, timeout=200)


@command(
    "project_copy_local",
    "Make a local copy of a shared project and open it. "
    "Make a local copy of a shared project (no rows; copied_from kept), then open it",
    req("path", "The shared project's folder."),
    opt("name", "Its name in the local folder (when its own is taken)."),
)
def project_copy_local(a: dict[str, Any]) -> Any:
    return api.call("POST", "/projects/copy-local", {k: a[k] for k in ("path", "name") if a.get(k)})


@command(
    "project_types",
    "The project types New project makes, explained. "
    "The project types New project makes, each explained for beginners",
    opt("put_away", "true/false: the page's explanations put away or shown.", "bool"),
)
def project_types(a: dict[str, Any]) -> Any:
    if a.get("put_away") is not None:
        api.call("POST", "/projects/explained", {"explained": a["put_away"] is True})
    return api.call("GET", "/projects/types")


@command(
    "project_files", "A project folder's files, as the Workbench opens them", req("folder", "Its folder.")
)
def project_files(a: dict[str, Any]) -> Any:
    return api.call("POST", "/projects/open", {"folder": a["folder"]})


@command(
    "project_export_data",
    "Export data.py again from data.ipynb. "
    "Export data.py again from the project's data.ipynb (data.py edited by hand: refused unless replace)",
    req("folder", "The project's folder."),
    opt("replace", "Replace a data.py edited by hand.", "bool"),
)
def project_export_data(a: dict[str, Any]) -> Any:
    return api.call(
        "POST", "/projects/export-data", {"folder": a["folder"], "replace": bool(a.get("replace"))}
    )


@command(
    "project_dictionary",
    "The data dictionary of a project's data.ipynb. "
    "The data dictionary of a project's data.ipynb (as saved): each table's columns, plain types, "
    "descriptions, where each comes from (the open window's: workbench_window dictionary.list)",
    req("folder", "The project's folder."),
)
def project_dictionary(a: dict[str, Any]) -> Any:
    return api.call("POST", "/projects/dictionary", {"folder": a["folder"]})


@command(
    "project_installs",
    "What the open project needs installed, and its state. "
    "What the open project needs installed, found as it opens and installed at once (the progress bar's "
    "state): each package, why it is needed and its status; check looks again; install runs it (waits for "
    "Allow)",
    opt("action", "state (default), check or install."),
)
def project_installs(a: dict[str, Any]) -> Any:
    action = str(a.get("action") or "state")
    if action == "state":
        return api.call("GET", "/project/installs")
    if action == "check":
        return api.call("POST", "/project/installs/check", {}, timeout=120)
    if action == "install":
        return api.call("POST", "/project/installs/run", {}, timeout=900)
    raise CommandError("action is one of: state, check, install.")
