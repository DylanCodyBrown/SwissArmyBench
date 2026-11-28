"""The agent's app_* commands: the page itself: snapshots.

Registered into cli/commands.py's REGISTRY when it imports this module (the tool list's order is the areas',
then each command's place here). Standard library only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

from swissarmybench.cli import api
from swissarmybench.cli.command_kit import ImageResult, command, opt, req


@command(
    "app_snapshot",
    "A PNG of the app as the user sees it. Your scroll, selection, splits and panels. Shows real "
    "cell values, and the user's browser tab must be visible.",
    opt("area", "app (the whole window, default), ribbon, grid, steps, analyze or projects."),
    opt("scale", "1 (default) or 2 for a sharper picture.", "int"),
    opt("out", "Also save the PNG to this file path."),
    image=True,
)
def app_snapshot(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("area", "scale") if a.get(k) is not None}
    data, headers = api.fetch_bytes("POST", "/snapshots", body, timeout=45.0)
    meta: dict[str, Any] = {"area": headers.get("x-snapshot-area"), "bytes": len(data)}
    for key in ("width", "height"):
        if headers.get(f"x-snapshot-{key}", "").isdigit():
            meta[key] = int(headers[f"x-snapshot-{key}"])
    if a.get("out"):
        path = Path(a["out"]).expanduser()
        path.write_bytes(data)
        meta["saved"] = str(path)
    return ImageResult(data, meta)


@command(
    "app_screen",
    "What the user sees now, as text (names only). "
    "What the user is looking at right now, as text: every window in brief (the focused one first), or one in "
    "full (its page, open tab and document, cursor line, selection, dialogs, errors, the table in front). "
    "Instant: read from memory, no page is asked. Names only, never a cell's value; app_snapshot for a picture",
    opt(
        "window", "One window in full: its id from the list (w1), focused, or its kind (tables, scripts...)."
    ),
)
def app_screen(a: dict[str, Any]) -> Any:
    if a.get("window"):
        return api.call("GET", f"/screen/{quote(str(a['window']), safe='')}")
    return api.call("GET", "/screen")


# widgets on the Canvas (the Streamlit extension's canvas_* and widgets_*; app notebooks went, 2026-11-21).
@command(
    "app_mode",
    "The open project's mode: its type and working set. "
    "The open project's mode: its type and working set (canvases, blade families, languages, cell kinds, "
    "your tool group, the export); every with all: each type this app can make",
    opt("all", "true: every project type this app can make (New project's list).", "bool"),
    opt("areas", "true: the rail's areas the on extensions add.", "bool"),
)
def app_mode(a: dict[str, Any]) -> Any:
    if a.get("areas"):
        return api.call("GET", "/app/areas")
    return api.call("GET", "/app/modes" if a.get("all") else "/app/mode")


@command(
    "app_gates",
    "The features the project's type keeps closed. "
    "The features the open project's type keeps closed (your tools stay open); every=true or false is "
    "Settings' Open every feature in this project",
    opt("every", "true: open every feature in this project; false: keep its type's gates.", "bool"),
)
def app_gates(a: dict[str, Any]) -> Any:
    if a.get("every") is None:
        return api.call("GET", "/app/gates")
    return api.call("POST", "/app/gates", {"every": bool(a["every"])})


@command(
    "app_session",
    "The Session log: what changed this session. "
    "The Session page's log: what you (and the user) made or changed this session, newest first, each "
    "with its area and its object; and whether the user follows you (their switch, read-only to you)",
    opt("who", "agent (default), user or both."),
    opt("limit", "Default 200.", "int"),
    opt("changes", "true: only the entries that changed something (the page's Changes).", "bool"),
)
def app_session(a: dict[str, Any]) -> Any:
    params = {k: a.get(k) for k in ("who", "limit")} | ({"changes": "1"} if a.get("changes") else {})
    return api.call("GET", "/session-log", params=params)


@command(
    "app_beta_mode",
    "Beta mode; `on` sets it. "
    "Beta mode: the beta log and right-click notes (kept across restarts); `on` sets it",
    opt("on", "true or false; none: read it.", "bool"),
)
def app_beta_mode(a: dict[str, Any]) -> Any:
    if a.get("on") is not None:
        return api.call("PUT", "/beta", {"on": a["on"]})
    return api.call("GET", "/beta")


@command(
    "app_beta_log",
    "The beta log, newest last. Errors and stacks, slow requests, processes, page errors, notes",
    opt("kind", "e.g. error,page (start stop error refused slow process page note)."),
    opt("since", '"30m", "2h", "7d".'),
    opt("limit", "Default 200.", "int"),
)
def app_beta_log(a: dict[str, Any]) -> Any:
    return api.call("GET", "/beta/log", params={k: a.get(k) for k in ("kind", "since", "limit")})


@command("app_beta_notes", "The user's beta notes: words, element, last actions")
def app_beta_notes(a: dict[str, Any]) -> Any:
    return api.call("GET", "/beta/notes")


@command("app_beta_log_clear", "Clear the beta log, notes and pictures")
def app_beta_log_clear(a: dict[str, Any]) -> Any:
    return api.call("DELETE", "/beta/log")


@command(
    "app_beta_log_export",
    "The beta log and notes as one zip. Yours without the pictures",
    req("path", "A .zip path."),
)
def app_beta_log_export(a: dict[str, Any]) -> Any:
    return api.call("POST", "/beta/export", {"path": a["path"]})


@command(
    "app_update_check",
    "The running and latest versions; now, on. "
    "Version running, the latest, whether an update is available; `now` checks again, `on` sets the switch",
    opt("now", "true: ask the release list now.", "bool"),
    opt("on", "Check for updates: true or false (kept).", "bool"),
)
def app_update_check(a: dict[str, Any]) -> Any:
    if a.get("on") is not None:
        api.call("PUT", "/updates", {"check": a["on"]})
    if a.get("now"):
        return api.call("POST", "/updates/check", {"asked": True})
    return api.call("GET", "/updates")


@command(
    "app_update",
    "Update to the available version (on Allow). "
    "Update to the available version (waits for the user's Allow; the app stops, installs it, restarts)",
    opt("version", "The version app_update_check offers."),
)
def app_update(a: dict[str, Any]) -> Any:
    return api.call("POST", "/updates/install", {"version": a.get("version")}, timeout=200)


@command(
    "app_whats_new",
    "What's New: the releases since last seen. "
    "What's New (WHATSNEW.md): the releases since the version last seen; `since` or `all`; `open` shows the window",
    opt("since", "Releases newer than this version."),
    opt("all", "true: every release.", "bool"),
    opt("open", "true: open the window on the user's screen (closing it is the user's).", "bool"),
)
def app_whats_new(a: dict[str, Any]) -> Any:
    if a.get("open"):
        api.call("POST", "/whats-new/open", {})
    if a.get("all"):
        return api.call("GET", "/whats-new?all=1")
    if a.get("since"):
        return api.call("GET", f"/whats-new?since={quote(str(a['since']), safe='')}")
    return api.call("GET", "/whats-new")


@command(
    "app_lifecycle",
    "When the server stops, and why. "
    "When the server stops: windows open, the last client, busy, held, seconds left (it lives while the app is open)",
)
def app_lifecycle(a: dict[str, Any]) -> Any:
    return api.call("GET", "/lifecycle")


@command(
    "app_registration_list",
    "The library's app registrations. Their three variable names, the connections using each, the last check",
    opt("name", "One registration: it and its last access report."),
    opt("connection", "A connection's Access section instead."),
)
def app_registration_list(a: dict[str, Any]) -> Any:
    if a.get("connection"):
        return api.call("GET", f"/connections/{quote(str(a['connection']), safe='')}/access")
    if a.get("name"):
        return api.call("GET", f"/app-registrations/{quote(str(a['name']), safe='')}")
    return api.call("GET", "/app-registrations")


@command(
    "app_registration_add",
    "Add an app registration (three variable names). "
    "Add an app registration to the library: its name and the VARIABLES holding its tenant id, client id and "
    "client secret (names only; remove=true takes it away)",
    req("name", "Its name."),
    opt("tenant", "The variable holding its tenant id."),
    opt("client", "The variable holding its client id."),
    opt("secret", "The variable holding its client secret (a keyring or vault variable)."),
    opt("remove", "true: remove it from the library.", "bool"),
)
def app_registration_add(a: dict[str, Any]) -> Any:
    if a.get("remove"):
        return api.call("POST", "/app-registrations/remove", {"name": a["name"]})
    body = {k: a[k] for k in ("name", "tenant", "client", "secret") if a.get(k)}
    return api.call("POST", "/app-registrations", body)


def _registration_check(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/app-registrations/{quote(str(a['name']), safe='')}/check", {}, timeout=200)


command(
    "app_registration_test",
    "Test an app registration: its access report. "
    "Test an app registration: its access report made now (read-only calls; never a token or a row kept)",
    req("name", "The registration."),
)(_registration_check)


command(
    "app_registration_check",
    "Check again what an app registration reaches. Workspaces, datasets, each connection using it; "
    "kept as names and marks",
    req("name", "The registration."),
)(_registration_check)


@command(
    "app_claude",
    "Which Claude Code and Claude Desktop are installed. "
    "Which Claude Code and Claude Desktop this computer has (Launch Claude)",
    opt("refresh", "true: look for Claude again.", "bool"),
)
def app_claude(a: dict[str, Any]) -> Any:
    # Reading only: launching Claude and choosing which one is launched are the user's (403 for the agent).
    return api.call("GET", "/claude?refresh=1" if a.get("refresh") else "/claude")


@command(
    "app_context",
    "context.md: the app's live picture. "
    "context.md: connections (their SQL names), open tables, the ERD, variables, documents, windows, the guide",
)
def app_context(a: dict[str, Any]) -> Any:
    # The same text as Launch Claude's folder's context.md and the resource swissarmybench://context.
    return api.call("GET", "/claude/context")


@command(
    "app_audit",
    "The audit log's last entries (never cell values). "
    "The audit log's last entries: who did what (never cell values)",
)
def app_audit(a: dict[str, Any]) -> Any:
    return api.call("GET", "/audit")


@command(
    "app_navigate",
    "Move a window: home, back, forward, a view, pop. "
    "Move a window as the user does: home (the mark: the Projects page), back, forward, or a view",
    req(
        "to",
        "the rail: projects (the mark), data (browse tables), tables (or grids), analyze, erd, notebooks, "
        "scripts, apps, blades, connections, environment, structures, session, settings; back, forward, "
        "add_connection, add_api; home: "
        "new_sql (a new SQL file on the Scripts page; new_sql:<connection> its header set; new_query and query "
        "read as it), grid:<id>; "
        "scripts (its Blades pane): blade:<name>, new_blade",
    ),
    opt("window", "home (default), notebooks, scripts or workbench (either: the one last used)."),
    opt("new_window", "notebooks, scripts, apps: true opens a Workbench window of its own.", "bool"),
    opt("pop", "`to` (a page, grid:<id>) in its own window: out, reattach, show; list."),
)
def app_navigate(a: dict[str, Any]) -> Any:
    if a.get("pop"):
        return _pop_out(str(a["pop"]), str(a["to"]))
    keys = ("to", "window", "new_window")
    return api.call("POST", "/navigate", {k: a[k] for k in keys if a.get(k) is not None})


# Pop out (the owner, 2026-11-27): any page or table in a window of its own, its old place blank with Reattach.
_POP_OUT = {"out": "/pop-outs", "reattach": "/pop-outs/reattach", "show": "/pop-outs/show"}


def _pop_out(action: str, to: str) -> Any:
    if action == "list":
        return api.call("GET", "/pop-outs")
    if action not in _POP_OUT:
        raise api.CommandError("pop is out, reattach, show or list.")
    kind, _, grid = to.partition(":")
    return api.call("POST", _POP_OUT[action], {"table": grid} if kind == "grid" and grid else {"page": to})


@command(
    "app_rail",
    "The rail's names beside its icons; labels sets it. "
    "The rail's names beside its icons (on by default); labels sets it",
    opt("labels", "true: names; false: icons only.", "bool"),
)
def app_rail(a: dict[str, Any]) -> Any:
    if a.get("labels") is not None:
        return api.call("PUT", "/rail", {"labels": a["labels"]})
    return api.call("GET", "/rail")


@command(
    "app_shutdown",
    "Stop the server. The tables close; this MCP stops answering until it starts again",
)
def app_shutdown(a: dict[str, Any]) -> Any:
    return api.call("POST", "/shutdown")
