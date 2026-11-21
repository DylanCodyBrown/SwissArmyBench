"""The Session page's log (the owner, 2026-11-16: "when the agent is driving the app and adding things,
I want to see objects that were created in a log make that a new page called Session on the rail").

Every action already goes to the audit log (adapters/state_files.py: who, what, which table, never a
cell value). This session's part of it, as the Session page lists it: what was made or changed, in
plain words, the area it is in, and the object itself (a grid, a card, a relationship, a connection,
a notebook's cell...) as a place the page can go to. Reads (describe, profile, rows) are not here:
they make nothing.

The rule the audit log keeps, kept harder: an entry is built only from names (tables, columns, files,
connections, cards' kinds) and counts. Never a query's text (`query` is dropped), a step's values, a
cell's value or a secret: each action's words are written here field by field, so a detail nobody
named never reaches the page. Pure rules, no I/O, no clock (the service stamps the time).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

# Where an entry's object lives: the rail's areas, and the project (the Projects page's).
AREAS: tuple[str, ...] = (
    "grids",
    "analyze",
    "erd",
    "notebooks",
    "scripts",
    "apps",
    "blades",
    "connections",
    "variables",
    "project",
)
ACTORS: tuple[str, ...] = ("agent", "user")
# The Session page's filter: the agent's entries (the default), the user's, or both.
FILTERS: tuple[str, ...] = ("agent", "user", "both")
DEFAULT_FILTER = "agent"
# Follow the agent (a switch on the Session page and in Settings): on until the user turns it off.
DEFAULT_FOLLOW = True
# This session's entries, newest kept (memory only: the audit log is the record on disk).
MAX_ENTRIES: int = 1000
MAX_NAME: int = 120
MAX_LISTED: int = 20

Entry = dict[str, Any]
Target = dict[str, Any] | None


class SessionLogError(ValueError):
    """A filter or a switch that is not one."""


def _name(value: Any) -> str:
    """A name as words: one line, trimmed (a name is metadata; a long one is cut, never a value)."""
    if value is None:
        return ""
    text = " ".join(str(value).split())
    return text if len(text) <= MAX_NAME else text[: MAX_NAME - 1] + "…"


def _file(value: Any) -> str:
    """A path's last part: a file or a folder's own name."""
    text = str(value or "").rstrip("/\\")
    return _name(re.split(r"[/\\]", text)[-1]) if text else ""


def _area_of_document(path: Any) -> str:
    text = str(path or "").lower()
    if text.endswith(".stapp.json"):
        return "apps"
    if text.endswith(".ipynb"):
        return "notebooks"
    return "scripts"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def relationship_key(from_table: str, from_columns: Any, to_table: str, to_columns: Any) -> str:
    """A relationship as the log names it: orders.customer_id -> customers.id (names only)."""
    left = ",".join(str(c) for c in from_columns)
    right = ",".join(str(c) for c in to_columns)
    return f"{from_table}.{left} -> {to_table}.{right}"


# ===== the objects: where each one is, as the page goes to it =====


def _grid(details: dict[str, Any], dataset: str) -> Target:
    grid = details.get("grid")
    return {"place": "grid", "grid": _name(grid), "dataset": dataset} if grid else _dataset(dataset)


def _analysis(details: dict[str, Any]) -> str:
    """An analysis by its everyday question (its contract's label), else its id."""
    from swissarmybench.domain.analysis_contracts import BY_ID

    found = BY_ID.get(str(details.get("analysis")))
    return found.label if found else _name(details.get("analysis")) or "an analysis"


def _dataset(dataset: str) -> Target:
    return {"place": "dataset", "dataset": dataset} if dataset else {"place": "area", "area": "grids"}


def _area(area: str) -> Target:
    return {"place": "area", "area": area}


def _document(path: Any, cell: Any = None) -> Target:
    if not path:
        return None
    number = cell if type(cell) is int else None
    return {"place": "cell" if number is not None else "document", "path": str(path), "cell": number}


# ===== each action's words =====
# (what, area, target), from the audit entry's own fields: `d` is the dataset argument (a table's name
# for most), `x` the details. None: not an entry of the Session page.

Said = tuple[str, str, Target]
Rule = Callable[[str, dict[str, Any]], Said | None]

_STEP_WORDS = {
    "add": "Added a {kind}step to {d}",
    "delete": "Removed a {kind}step from {d}",
    "edit": "Changed a {kind}step of {d}",
    "toggle": "Turned a step of {d} on or off",
    "move": "Moved a step of {d}",
}


def _steps(d: str, x: dict[str, Any]) -> Said:
    op = x.get("op")
    kind = _name(x.get("kind"))
    words = _STEP_WORDS.get(str(op))
    if words:
        what = words.format(kind=f"{kind} " if kind else "", d=d)
    else:
        what = f"Set the steps of {d} ({_plural(int(x.get('steps') or 0), 'step')})"
    return what, "grids", _grid(x, d)


def _relationships(d: str, x: dict[str, Any]) -> Said:
    added = [_name(k) for k in (x.get("added") or [])][:MAX_LISTED]
    removed = [_name(k) for k in (x.get("removed") or [])][:MAX_LISTED]
    parts = []
    if len(added) == 1:
        parts.append(f"Added the relationship {added[0]}")
    elif added:
        parts.append(f"Added {_plural(len(added), 'relationship')}")
    if len(removed) == 1:
        parts.append(f"{'removed' if parts else 'Removed'} the relationship {removed[0]}")
    elif removed:
        parts.append(f"{'removed' if parts else 'Removed'} {_plural(len(removed), 'relationship')}")
    what = ", ".join(parts) or "Changed the relationships"
    target: Target = {"place": "relationship", "relationships": added} if added else _area("erd")
    return what, "erd", target


def _blade(d: str, x: dict[str, Any], verb: str) -> Said:
    if x.get("kind") == "connection":
        return f"{verb} the connection {d}", "connections", {"place": "connection", "name": d}
    return f"{verb} the blade {d}", "blades", {"place": "blade", "name": d}


# The Workbench window's commands that make or change something (workbench_window), in words.
_WINDOW_WORDS: dict[str, str] = {
    "cell.insertAbove": "Added a cell to {t}",
    "cell.insertBelow": "Added a cell to {t}",
    "cell.addDax": "Added a DAX cell to {t}",
    "html.add": "Added an HTML cell to {t}",
    "snippet.insert": "Inserted a snippet into {t}",
    "cell.delete": "Deleted a cell of {t}",
    "cell.undo": "Undid a cell's change in {t}",
    "cell.moveUp": "Moved a cell of {t}",
    "cell.moveDown": "Moved a cell of {t}",
    "cell.toCode": "Made a cell of {t} a Python cell",
    "cell.toMarkdown": "Made a cell of {t} a Markdown cell",
    "cell.toSql": "Made a cell of {t} a SQL cell",
    "cell.toDax": "Made a cell of {t} a DAX cell",
    "cell.paste": "Pasted a cell into {t}",
    "cell.name": "Named a cell of {t}",
    "html.resize": "Sized an HTML cell of {t}",
    "file.newNotebook": "Made a new notebook",
    "file.newScript": "Made a new script",
    "file.newApp": "Made a new Streamlit app",
    "file.save": "Saved {t}",
    "file.saveAs": "Saved a copy of {t}",
    "file.exportScript": "Exported {t} as one script",
    "file.exportNotebook": "Exported {t} as one notebook",
    "tables.arrange": "Arranged the tables of {t}",
}


def _window(d: str, x: dict[str, Any]) -> Said | None:
    command = str(x.get("command") or "")
    words = _WINDOW_WORDS.get(command)
    if words is None:
        return None
    path = x.get("path")
    title = _name(x.get("title")) or _file(path) or "the document"
    target = _document(path, x.get("cell") if command.startswith(("cell.", "html.", "snippet.")) else None)
    return words.format(t=title), _area_of_document(path or x.get("title")), target


def _app_page(verb: str) -> Rule:
    def said(d: str, x: dict[str, Any]) -> Said:
        title = _name(x.get("title")) or d.split(": ")[0]
        detail = _name(x.get("detail"))
        return (
            f"{verb} {detail} in {title}" if detail else f"{verb} in {title}",
            "apps",
            _document(x.get("path")),
        )

    return said


def _export(d: str, x: dict[str, Any]) -> Said:
    file = _file(x.get("file"))
    fmt = _name(x.get("format")).upper()
    what = f"Exported {d} to {file}" if file else f"Exported {d}{f' as {fmt}' if fmt else ''}"
    return what, "grids", _dataset(d)


def _approval(d: str, x: dict[str, Any]) -> Said:
    request = _name(x.get("request")) or "request"
    verb = "Allowed" if x.get("approved") else "Refused"
    return (
        f"{verb} the agent's {request} of {d}" if d else f"{verb} the agent's {request}",
        "grids",
        _dataset(d),
    )


RULES: dict[str, Rule] = {
    # Grids: tables arriving, their steps, their highlights; a compare; an export (with its Allow).
    "open_grid": lambda d, x: (f"Opened {d} in a grid", "grids", _grid(x, d)),
    "push": lambda d, x: (f"Opened {d}", "grids", _dataset(d)),
    "load_file": lambda d, x: (
        f"Opened {_file(x.get('file'))} as {d}" if x.get("file") else f"Opened {d}",
        "grids",
        _dataset(d),
    ),
    "sql_query": lambda d, x: (f"Made {d} from a query", "grids", _dataset(d)),
    "sql_pin": lambda d, x: (f"Made {d} from SQL", "grids", _dataset(d)),
    "open_connection_table": lambda d, x: (f"Opened {d} from a connection", "grids", _dataset(d)),
    "close": lambda d, x: (f"Closed {d}", "grids", _area("grids")),
    "rename": lambda d, x: (f"Renamed {d} to {_name(x.get('to'))}", "grids", _dataset(_name(x.get("to")))),
    "steps": _steps,
    "undo": lambda d, x: (f"Undid a step change of {d}", "grids", _grid(x, d)),
    "redo": lambda d, x: (f"Redid a step change of {d}", "grids", _grid(x, d)),
    "highlights": lambda d, x: (
        f"Highlighted rows of {d} ({_plural(int(x.get('count') or 0), 'rule')})",
        "grids",
        _grid(x, d),
    ),
    "compare": lambda d, x: (f"Compared {d.replace(':', ' with ', 1)}", "grids", _area("grids")),
    "export": _export,
    "approval": _approval,
    # Analyze: a run (its cards land by themselves), a fix applied as steps, cards and dashboards.
    "analyze_run": lambda d, x: (
        f"Ran {_analysis(x)} on {d} ({_count(x.get('cards'), 'card')} on Analyze)",
        "analyze",
        _area("analyze"),
    ),
    "analyze_fix": lambda d, x: (
        f"Made {d} fit {_analysis(x)} ({_count(x.get('fixes'), 'fix').replace('fixs', 'fixes')}, as steps)",
        "analyze",
        _grid(x, d),
    ),
    "add_card": lambda d, x: (
        f"{'Replaced' if x.get('replaced') else 'Added'} a {_name(x.get('kind')) or 'new'} card on Analyze",
        "analyze",
        {"place": "card", "card": _name(x.get("card"))} if x.get("card") else _area("analyze"),
    ),
    "update_card": lambda d, x: (
        "Changed a card on Analyze",
        "analyze",
        {"place": "card", "card": _name(x.get("card"))} if x.get("card") else _area("analyze"),
    ),
    "remove_card": lambda d, x: (
        "Removed a card from Analyze",
        "analyze",
        _area("analyze"),
    ),
    "save_dashboard": lambda d, x: (f"Saved the dashboard {d}", "analyze", _area("analyze")),
    "open_dashboard": lambda d, x: (f"Opened the dashboard {d}", "analyze", _area("analyze")),
    "delete_dashboard": lambda d, x: (
        f"Deleted the dashboard {d}",
        "analyze",
        _area("analyze"),
    ),
    # The ERD: relationships, each one added named; a set saved, renamed or deleted; joins deleted or changed.
    "relationships": _relationships,
    "save_relationship_set": lambda d, x: (
        f"Saved the relationships as {_name(x.get('set'))}",
        "erd",
        _area("erd"),
    ),
    "save_tang": lambda d, x: (f"Saved the relationships as {_name(x.get('tang'))}", "erd", _area("erd")),
    "rename_relationship_set": lambda d, x: (
        f"Renamed the saved set {_name(x.get('set'))} to {_name(x.get('to'))}",
        "erd",
        _area("erd"),
    ),
    "delete_relationship_set": lambda d, x: (
        f"Deleted the saved set {_name(x.get('set'))}",
        "erd",
        _area("erd"),
    ),
    "relationships_delete": lambda d, x: (
        f"Deleted {_count(x.get('removed'), 'relationship')}",
        "erd",
        _area("erd"),
    ),
    "relationships_update": lambda d, x: (
        f"Changed {_count(x.get('changed'), 'relationship')}",
        "erd",
        _area("erd"),
    ),
    # Connections and blades.
    "connection_slot_waited": lambda d, x: (
        f"Waited {_name(x.get('seconds'))} s for a slot on {d}",
        "connections",
        {"place": "connection", "name": d},
    ),
    "connection_limits": lambda d, x: (
        f"Set {d} to {_name(x.get('total'))} queries at once, {_name(x.get('agent'))} of them the agent's",
        "connections",
        {"place": "connection", "name": d},
    ),
    "save_blade": lambda d, x: _blade(d, x, "Saved"),
    "remove_blade": lambda d, x: (
        f"Removed the {'connection' if x.get('kind') == 'connection' else 'blade'} {d}",
        "connections" if x.get("kind") == "connection" else "blades",
        _area("connections" if x.get("kind") == "connection" else "blades"),
    ),
    "copy_blade": lambda d, x: (
        f"Copied {_name(x.get('of'))} as {d}",
        "blades",
        {"place": "blade", "name": d},
    ),
    "import_blades": lambda d, x: (f"Imported {d}", "blades", _area("blades")),
    "add_api": lambda d, x: (
        f"Added the API {_name(x.get('connection')) or d.split(':')[0]}",
        "apis",
        _area("apis"),
    ),
    "api_call": lambda d, x: (
        f"Called {_name(x.get('api'))} {_name(x.get('operation'))} ({_name(x.get('status'))})",
        "structures",
        _area("structures"),
    ),
    "api_refresh": lambda d, x: (f"Read the API {_name(x.get('api'))} again", "apis", _area("apis")),
    "api_delete": lambda d, x: (f"Deleted the API {_name(x.get('api'))}", "apis", _area("apis")),
    # Structures: names only, never a value.
    "structure_open": lambda d, x: (
        f"Opened the structure {_name(x.get('structure'))}",
        "structures",
        _area("structures"),
    ),
    "structure_new": lambda d, x: (
        f"Made the structure {_name(x.get('structure'))}",
        "structures",
        _area("structures"),
    ),
    "structure_paste": lambda d, x: (
        f"Pasted the structure {_name(x.get('structure'))}",
        "structures",
        _area("structures"),
    ),
    "structure_step": lambda d, x: (
        f"Added a {_name(x.get('step'))} step to {_name(x.get('structure'))}",
        "structures",
        _area("structures"),
    ),
    "structure_save": lambda d, x: (
        f"Saved the structure {_name(x.get('structure'))}",
        "structures",
        _area("structures"),
    ),
    "structure_save_as": lambda d, x: (
        f"Saved the structure {_name(x.get('structure'))}",
        "structures",
        _area("structures"),
    ),
    "structure_to_grid": lambda d, x: (
        f"Opened {d} from the structure {_name(x.get('structure'))}",
        "grids",
        {"place": "dataset", "dataset": d},
    ),
    "load_catalog": lambda d, x: (
        f"Loaded the catalog of {d}",
        "connections",
        {"place": "connection", "name": d},
    ),
    "connection_colour": lambda d, x: (
        f"Coloured the connection {d} {_name(x.get('colour')) or 'the next free colour'}",
        "connections",
        {"place": "connection", "name": d},
    ),
    "remove_catalog": lambda d, x: (f"Removed the catalog of {d}", "connections", _area("connections")),
    # The Workbench: documents and their cells.
    "workbench_window": _window,
    "save_document": lambda d, x: (f"Saved {_file(d)}", _area_of_document(d), _document(d)),
    "export_notebook": lambda d, x: (f"Exported {_file(d)}", "notebooks", _document(d)),
    "export_script": lambda d, x: (f"Exported {_file(d)}", "scripts", _document(d)),
    # Streamlit apps: the canvas's pages and blocks.
    "streamlit_add_page": _app_page("Added the page"),
    "streamlit_change_page": _app_page("Changed the page"),
    "streamlit_remove_page": _app_page("Removed the page"),
    "streamlit_place_block": _app_page("Placed the block"),
    "streamlit_change_block": _app_page("Changed the block"),
    "streamlit_remove_block": _app_page("Removed the block"),
    "export_streamlit_app": lambda d, x: (f"Exported a Streamlit app to {_file(d)}", "apps", None),
    "save_streamlit_app_as": lambda d, x: (f"Saved a Streamlit app as {_file(d)}", "apps", None),
    # Variables (the Variables page): names only, never a value.
    "add_variable": lambda d, x: (f"Added the variable {d}", "variables", _area("variables")),
    "change_variable": lambda d, x: (f"Changed the variable {d}", "variables", _area("variables")),
    "rename_variable": lambda d, x: (
        f"Renamed the variable {d} to {_name(x.get('to'))}",
        "variables",
        _area("variables"),
    ),
    "remove_variable": lambda d, x: (f"Removed the variable {d}", "variables", _area("variables")),
    # The project.
    "new_sab_project": lambda d, x: (f"Made the project {_name(x.get('name'))}", "project", _area("project")),
    "open_sab_project": lambda d, x: ("Opened a project", "project", _area("project")),
    "save_sab_project": lambda d, x: (
        "Saved the project with its rows" if x.get("rows") else "Saved the project",
        "project",
        _area("project"),
    ),
    "close_sab_project": lambda d, x: ("Closed the project", "project", _area("project")),
    "project_import": lambda d, x: ("Imported into the project", "project", _area("project")),
    "new_project": lambda d, x: (f"Made the project folder {_file(d)}", "project", _area("project")),
    "export_data": lambda d, x: ("Exported data.py", "notebooks", _document(d)),
    # Settings' Team box (one GitHub repository for the team library and its projects).
    "team_join": lambda d, x: ("Joined a team", "project", None),
    "team_start": lambda d, x: (f"Started a team ({x.get('files')} files pushed)", "project", None),
    "team_leave": lambda d, x: ("Left the team", "project", None),
    # Share a running app with the organization (Microsoft Dev Tunnels): which app, never its link.
    "share_install": lambda d, x: ("Installed devtunnel (for sharing apps)", "apps", None),
    "share_sign_in": lambda d, x: ("Signed in to share apps with the organization", "apps", None),
    "share_start": lambda d, x: (f"Shared {d} with the organization", "apps", None),
    "share_stop": lambda d, x: (
        f"Stopped sharing {d}"
        + (f" ({_name(x.get('why'))})" if x.get("why") not in (None, "stopped") else ""),
        "apps",
        None,
    ),
}


def entry(actor: Any, action: Any, dataset: Any, details: dict[str, Any]) -> Entry | None:
    """The Session page's entry for one audit entry (no id, no time: the service adds them), or None
    when the action makes nothing. Built from names and counts only."""
    if actor not in ACTORS or not isinstance(action, str):
        return None
    rule = RULES.get(action)
    if rule is None:
        return None
    said = rule(_name(dataset), details)
    if said is None:
        return None
    what, area, target = said
    return {"actor": actor, "action": action, "what": what, "area": area, "target": target}


def check_filter(value: Any) -> str:
    if value in (None, ""):
        return DEFAULT_FILTER
    if value not in FILTERS:
        raise SessionLogError(f"who is one of {', '.join(FILTERS)}.")
    return str(value)


def shown(entries: list[Entry], who: str, limit: int) -> list[Entry]:
    """The entries the filter shows, newest first, at most `limit`."""
    kept = [e for e in reversed(entries) if who == "both" or e["actor"] == who]
    return kept[: max(0, limit)]


def check_follow(body: Any) -> bool:
    on = body.get("on") if isinstance(body, dict) else None
    if not isinstance(on, bool):
        raise SessionLogError('Send {"on": true} or {"on": false}.')
    return on


def read_saved(saved: Any) -> bool:
    """Follow the agent as last chosen (follow.json), else on."""
    if isinstance(saved, dict) and isinstance(saved.get("follow"), bool):
        return bool(saved["follow"])
    return DEFAULT_FOLLOW


def _count(raw: object, word: str) -> str:
    n = raw if isinstance(raw, int) else 0
    return f"{n} {word}{'' if n == 1 else 's'}"
