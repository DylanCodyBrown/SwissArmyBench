"""The Streamlit extension's agent commands (the golden rule: every action on its canvas and live cells is one
of these). The base's registry (swissarmybench/cli/commands.py) takes them when the extension is on, so each
is an MCP tool and a `sab` command too; with it off, a call says which extension it needs. Standard library
only (the `sab` command reads them).

A Streamlit app is a document of its own: pages of blocks, each block a link to a Python, Markdown or HTML
cell of a notebook or script (a Markdown or HTML cell is st.markdown or st.html on the page). There is no
Streamlit kind of cell: a Python cell that calls Streamlit is shown live in its cell. The window's commands
work on what is in front; the streamlit_* commands on an app by its id.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.commands import Command, CommandError, Registrar, _q, _window, opt, req

COMMANDS: dict[str, Command] = {}


command = Registrar(COMMANDS)


@command("workbench_new_app", "A new Streamlit app (an empty canvas) as a Workbench tab")
def workbench_new_app(a: dict[str, Any]) -> Any:
    return _window("file.newApp", {})


@command(
    "workbench_canvas",
    "The front canvas: its app id (for streamlit_*), page, blocks or live page",
)
def workbench_canvas(a: dict[str, Any]) -> Any:
    return _window("canvas.state", {})


@command(
    "workbench_canvas_play",
    "Play the front canvas: the live page in place",
    opt("page", "The page to show (its id; default: the one in front)."),
)
def workbench_canvas_play(a: dict[str, Any]) -> Any:
    return _window("canvas.play", {"page": a["page"]} if a.get("page") else {})


@command("workbench_canvas_edit", "Back from the live page to the front canvas's blocks")
def workbench_canvas_edit(a: dict[str, Any]) -> Any:
    return _window("canvas.edit", {})


@command(
    "streamlit_cells",
    "Every Python cell that calls Streamlit, and every Markdown and HTML cell (kind), by document (the "
    "Streamlit cells pane)",
    opt("folder", "A project's folder: its files on disk too."),
)
def streamlit_cells(a: dict[str, Any]) -> Any:
    folder = f"?folder={_q(a['folder'])}" if a.get("folder") else ""
    return api.call("GET", "/streamlit/cells" + folder)


@command(
    "workbench_live_cells",
    "The front document's cells that call Streamlit (shown live): makes, reads, state",
)
def workbench_live_cells(a: dict[str, Any]) -> Any:
    return _window("streamlit.list", {})


@command("workbench_live_run", "Run the front document's live cells")
def workbench_live_run(a: dict[str, Any]) -> Any:
    return _window("streamlit.run", {})


@command(
    "workbench_live_resize",
    "Size a live cell's pane in the front document",
    req("number", "The cell's own number.", "int"),
    opt("height", "Pixels, 60 to 2000 (without it: the usual height).", "int"),
)
def workbench_live_resize(a: dict[str, Any]) -> Any:
    args = {"number": a["number"]} | ({"height": a["height"]} if a.get("height") is not None else {})
    return _window("streamlit.resize", args)


@command("streamlit_apps", "The open Streamlit apps: canvases, and each open document's own")
def streamlit_apps(a: dict[str, Any]) -> Any:
    return api.call("GET", "/streamlit/apps")


@command(
    "streamlit_open",
    "Open a Streamlit app's file (a canvas) without the window",
    opt("path", "A .stapp.json file (without it: a new canvas)."),
)
def streamlit_open(a: dict[str, Any]) -> Any:
    body = {"path": a["path"]} if a.get("path") else {"canvas": True, "pages": []}
    return api.call("POST", "/streamlit/apps", body)


@command(
    "streamlit_app",
    "A canvas's pages, blocks (link, place, makes, reads, state, missing) and problems",
    req("app", "The app's id (streamlit_apps lists them)."),
)
def streamlit_app(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/streamlit/apps/{_q(a['app'])}")


@command(
    "streamlit_run",
    "Play a canvas: its pages from the linked cells as they are now, tables read again",
    req("app", "The app's id."),
)
def streamlit_run(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/streamlit/apps/{_q(a['app'])}/run")


@command(
    "streamlit_page_settings",
    "A canvas's page settings: title, icon, layout (wide, centered), logo, colours (theme)",
    req("app", "The app's id."),
    req("settings", '{"title": "Sales", "layout": "centered", "colours": {"primary": "#c8102e"}}', "json"),
)
def streamlit_page_settings(a: dict[str, Any]) -> Any:
    return api.call("PUT", f"/streamlit/apps/{_q(a['app'])}/settings", a["settings"])


@command(
    "streamlit_state",
    "The live page's session state (State panel): each key, its value, its block",
    req("app", "The app's id."),
)
def streamlit_state(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/streamlit/apps/{_q(a['app'])}/session")


@command(
    "streamlit_address",
    "A running app's addresses: the app, each page, each live cell",
    req("app", "The app's id."),
)
def streamlit_address(a: dict[str, Any]) -> Any:
    state = api.call("GET", f"/streamlit/apps/{_q(a['app'])}")
    if not state["running"]:
        return {"running": False, "problem": state["problem"], "hint": "streamlit_run starts it."}
    base = state["address"].rsplit(state["path"], 1)[0]
    return {
        "running": True,
        "app": state["address"],
        "pages": {p["name"]: base + p["address"] for p in state.get("pages", []) if p["address"]},
        "cells": {p["cell"]: base + p["preview"] for p in state.get("pieces", []) if p["preview"]},
    }


@command("streamlit_stop", "Stop a Streamlit app's process", req("app", "The app's id."))
def streamlit_stop(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/streamlit/apps/{_q(a['app'])}/stop")


@command("streamlit_close", "Close a Streamlit app opened with streamlit_open", req("app", "The app's id."))
def streamlit_close(a: dict[str, Any]) -> Any:
    return api.call("DELETE", f"/streamlit/apps/{_q(a['app'])}")


@command(
    "streamlit_install",
    "Install Streamlit into the app's Python (when streamlit_run says so)",
    req("app", "The app's id."),
)
def streamlit_install(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/streamlit/apps/{_q(a['app'])}/install")


@command(
    "streamlit_save",
    "Save a canvas to its file (.stapp.json: pages, blocks, links, page settings; no code)",
    req("app", "The app's id."),
    opt("path", "Where (default: the file it was opened from)."),
)
def streamlit_save(a: dict[str, Any]) -> Any:
    state = api.call("GET", f"/streamlit/apps/{_q(a['app'])}")
    path = a.get("path") or state["document"]
    if not path:
        raise CommandError("Send path: this app has no file yet.")
    if not path.lower().endswith(".stapp.json"):
        path += ".stapp.json"
    saved = api.call(
        "POST",
        "/workbench/save",
        {"path": path, "pages": state["pages"], "settings": state.get("settings"), "force": True},
    )
    api.call("PUT", f"/streamlit/apps/{_q(a['app'])}", {"document": saved["path"]})
    return saved


@command(
    "streamlit_export",
    "Export a canvas as an app that runs alone (app.py, pages, the tables' rows as Parquet). Waits for "
    "the user's approval click (the folder and the tables it copies); declined, nothing is written.",
    req("app", "The app's id."),
    req("folder", "Where it goes (made when it is not there)."),
)
def streamlit_export(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/streamlit/apps/{_q(a['app'])}/export", {"folder": a["folder"]})


@command(
    "streamlit_save_as",
    "Save as: the app's project as one zip (data.py, pages/*.py, sources); no rows, no secrets. A project "
    "with no data.ipynb gets one first: when it would hold a pasted table's rows, waits for the user's approval click",
    req("app", "The app's id (saved: its folder is the project)."),
    req("path", "The zip's path."),
)
def streamlit_save_as(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/streamlit/apps/{_q(a['app'])}/save-as", {"path": a["path"]})


@command(
    "streamlit_page_add",
    "Add a page to a canvas",
    req("app", "The app's id."),
    opt("name", "The page's name (default: Page N)."),
)
def streamlit_page_add(a: dict[str, Any]) -> Any:
    return api.call(
        "POST", f"/streamlit/apps/{_q(a['app'])}/pages", {"name": a["name"]} if a.get("name") else {}
    )


@command(
    "streamlit_page_change",
    "Rename a canvas's page, or move it among the pages",
    req("app", "The app's id."),
    req("page", "The page's id (p1...)."),
    opt("name", "Its new name."),
    opt("index", "Its new place among the pages, from 0.", "int"),
)
def streamlit_page_change(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("name", "index") if a.get(k) is not None}
    return api.call("PATCH", f"/streamlit/apps/{_q(a['app'])}/pages/{_q(a['page'])}", body)


@command(
    "streamlit_page_remove",
    "Remove a page from a canvas",
    req("app", "The app's id."),
    req("page", "The page's id."),
)
def streamlit_page_remove(a: dict[str, Any]) -> Any:
    return api.call("DELETE", f"/streamlit/apps/{_q(a['app'])}/pages/{_q(a['page'])}")


@command(
    "streamlit_block_place",
    "Place a Python, Markdown or HTML cell's link on a canvas's page (as dragging it there)",
    req("app", "The app's id."),
    req("page", "The page's id."),
    req("document", "The saved notebook's or script's path."),
    req("cell", "The cell's own number.", "int"),
    opt("row", "Its row, from 1 (default: after the last block).", "int"),
    opt("column", "The column it starts in, 1 to 12.", "int"),
    opt("w", "Its width in columns, 2 to 12 (default 6).", "int"),
    opt("h", "Its height in 40-pixel rows (default: its content's).", "int"),
)
def streamlit_block_place(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("document", "cell", "row", "column", "w", "h") if a.get(k) is not None}
    return api.call("POST", f"/streamlit/apps/{_q(a['app'])}/pages/{_q(a['page'])}/blocks", body)


@command(
    "streamlit_block_change",
    "Move or resize a block on the 12-column grid, or send it to another page",
    req("app", "The app's id."),
    req("page", "The page's id."),
    req("block", "The block's id (b1...: streamlit_app lists them)."),
    opt("row", "Its row, from 1.", "int"),
    opt("column", "The column it starts in, 1 to 12.", "int"),
    opt("insert", "true: a new row at `row`.", "bool"),
    opt("w", "Its width in columns, 2 to 12.", "int"),
    opt("h", "Its height in 40-pixel rows; 0: its content's.", "int"),
    opt("to_page", "Another page's id, to send it there."),
    opt("parent", 'A container\'s id, to put it inside ("": back on the page).'),
    opt("slot", "Which of the container's slots (a column, a tab), from 0.", "int"),
    opt("hidden", "Hidden while designing.", "bool"),
    opt("locked", "Locked: the designer does not move or size it.", "bool"),
    opt("props", 'A container\'s own properties: {"widths": [2, 1]}, {"labels": ["A", "B"]}...', "json"),
    opt(
        "view",
        'A SQL or DAX block\'s view: {"as": "table" | "bar" | "line" | "area" | "metric", "x", "y", '
        '"column", "label", "cache": false}; {} the table, cached.',
        "json",
    ),
)
def streamlit_block_change(a: dict[str, Any]) -> Any:
    body: dict[str, Any] = {k: a[k] for k in ("row", "column", "insert", "w") if a.get(k) is not None}
    if a.get("h") is not None:
        body["h"] = a["h"] or None
    if a.get("to_page"):
        body["page"] = a["to_page"]
    if a.get("parent") is not None:
        body["parent"] = a["parent"] or None
    body |= {k: a[k] for k in ("slot", "hidden", "locked", "props", "view") if a.get(k) is not None}
    path = f"/streamlit/apps/{_q(a['app'])}/pages/{_q(a['page'])}/blocks/{_q(a['block'])}"
    return api.call("PATCH", path, body)


@command(
    "streamlit_block_remove",
    "Take a block off its page",
    req("app", "The app's id."),
    req("page", "The page's id."),
    req("block", "The block's id."),
)
def streamlit_block_remove(a: dict[str, Any]) -> Any:
    path = f"/streamlit/apps/{_q(a['app'])}/pages/{_q(a['page'])}/blocks/{_q(a['block'])}"
    return api.call("DELETE", path)


# A canvas page's controllers (docs/ideas.md, controllers, 2026-11-15): a cell's header line
# `# Makes: region: str = "All"; by_region: table = orders` is its contract.


@command(
    "streamlit_check",
    "A canvas's contract check: defaults used, contract problems, names made twice, cycles; controllers",
    req("app", "The app's id."),
    opt("page", "One page's id (default: every page)."),
)
def streamlit_check(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/streamlit/apps/{_q(a['app'])}/check", params={"page": a.get("page")})


@command(
    "streamlit_test",
    "Test this page: AppTest tries each controller's values; each block's failures",
    req("app", "The app's id."),
    req("page", "The page's id."),
)
def streamlit_test(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/streamlit/apps/{_q(a['app'])}/pages/{_q(a['page'])}/test")


@command(
    "workbench_canvas_move_to_data",
    "Move a front-canvas block's model work (filter, group, join) into a named cell of data.ipynb",
    req("block", "The block's id (its thin hint: streamlit_app)."),
)
def workbench_canvas_move_to_data(a: dict[str, Any]) -> Any:
    return _window("canvas.moveToData", {"block": a["block"]})


# The canvas's property pane and designer (the owner, 2026-11-19): whatever is selected, what it uses, its
# Streamlit state and cache. A change to a cell's CODE is made in its open document by the window that holds
# the app (like typing; the editor's Undo takes it back): only the characters it names change. "Now" changes
# the RUNNING app only.


def _code_path(a: dict[str, Any]) -> str:
    return f"/streamlit/apps/{_q(a['app'])}/pages/{_q(a['page'])}/blocks/{_q(a['block'])}/code"


_BLOCK = (req("app", "The app's id."), req("page", "The page's id."), req("block", "The block's id."))
_WIDGET = opt("widget", "Which element of its cell, from 0 (canvas_inspect lists them; default 0).", "int")


@command(
    "canvas_inspect",
    "The property pane: a block (properties, widgets, uses, used by, state, cache, exported code), a page, or "
    "the app",
    req("app", "The app's id."),
    opt("page", "A page's id (without it: the app)."),
    opt("block", "A block's id."),
)
def canvas_inspect(a: dict[str, Any]) -> Any:
    asked = {"page": a.get("page"), "block": a.get("block")}
    return api.call("GET", f"/streamlit/apps/{_q(a['app'])}/inspect", params=asked)


@command(
    "canvas_table",
    "A table a block uses: its columns and types, its grid's steps in words, its first rows",
    req("name", "The table's name as Python names it (canvas_inspect: uses.tables)."),
)
def canvas_table(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/streamlit/tables/{_q(a['name'])}")


@command(
    "canvas_set_default",
    "A widget's default (value=, index= or default= in its cell's code; a plain value only)",
    *_BLOCK,
    req("value", 'The default: 5, "North", ["a", "b"], true.', "json"),
    _WIDGET,
)
def canvas_set_default(a: dict[str, Any]) -> Any:
    body = {
        "do": "set",
        "widget": a.get("widget") or 0,
        "name": "default",
        "value": a["value"],
        "apply": True,
    }
    return api.call("POST", _code_path(a), body)


@command(
    "canvas_set_property",
    "A widget's property in its cell's code (label, options, key, help...): set to a plain value, or reset",
    *_BLOCK,
    req("name", "The property, as Streamlit names it."),
    opt("value", "Its value (JSON). Without it: reset (taken out of the call).", "json"),
    _WIDGET,
)
def canvas_set_property(a: dict[str, Any]) -> Any:
    body: dict[str, Any] = {"widget": a.get("widget") or 0, "name": a["name"], "apply": True}
    body |= {"do": "set", "value": a["value"]} if a.get("value") is not None else {"do": "reset"}
    return api.call("POST", _code_path(a), body)


@command(
    "canvas_bind",
    "Bind a widget's property: to a name another cell makes, a session state key, a variable, or an expression",
    *_BLOCK,
    req("name", "The property (value, options, disabled...)."),
    req("kind", "name, state, variable or expression."),
    req("target", "The name, the key, the variable, or the expression."),
    _WIDGET,
)
def canvas_bind(a: dict[str, Any]) -> Any:
    body = {"do": "bind", "widget": a.get("widget") or 0, "apply": True}
    return api.call("POST", _code_path(a), body | {k: a[k] for k in ("name", "kind", "target")})


@command(
    "canvas_add_handler",
    "A widget's event handler: a function stub in its cell and on_change= (or on_click=) set",
    *_BLOCK,
    _WIDGET,
    opt("event", "on_change, on_click, on_submit or on_select (default: the widget's own)."),
    opt("handler", "The function's name (default: on_<key>_<event>)."),
)
def canvas_add_handler(a: dict[str, Any]) -> Any:
    body = {"do": "handler", "widget": a.get("widget") or 0, "apply": True}
    return api.call("POST", _code_path(a), body | {k: a[k] for k in ("event", "handler") if a.get(k)})


@command(
    "canvas_set_cache",
    "A function's cache decorator in a cell's code: st.cache_data or st.cache_resource, its settings, or none",
    *_BLOCK,
    req("function", "The function's name (canvas_inspect: cache)."),
    opt("kind", "data, resource or none (default: data)."),
    opt("settings", '{"ttl": 600, "max_entries": 100, "show_spinner": false}; null resets one.', "json"),
    opt("document", "A cell this one calls: its file (canvas_inspect: cache)."),
    opt("cell", "That cell's number.", "int"),
)
def canvas_set_cache(a: dict[str, Any]) -> Any:
    kind = a.get("kind") or "data"
    body: dict[str, Any] = {
        "do": "cache",
        "function": a["function"],
        "kind": None if kind == "none" else kind,
    }
    body |= {k: a[k] for k in ("settings", "document", "cell") if a.get(k) is not None}
    return api.call("POST", _code_path(a), body | {"apply": True})


@command(
    "canvas_state_set",
    "Now: set a session state key in the RUNNING app (not the code), or forget it",
    req("app", "The app's id (playing)."),
    req("key", "The key (canvas_inspect: a widget's state_key; streamlit_state lists them)."),
    opt("value", "Its value (JSON).", "json"),
    opt("forget", "true: take the key out (its widget starts from its default).", "bool"),
)
def canvas_state_set(a: dict[str, Any]) -> Any:
    body: dict[str, Any] = {"key": a["key"]}
    body |= {"forget": True} if a.get("forget") else {"value": a.get("value")}
    return api.call("POST", f"/streamlit/apps/{_q(a['app'])}/now", body)


@command(
    "canvas_cache_clear",
    "Now: clear a cached function's cache in the RUNNING app (or every cache)",
    req("app", "The app's id (playing)."),
    opt("function", "The function's name (default: every cache)."),
)
def canvas_cache_clear(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/streamlit/apps/{_q(a['app'])}/now", {"clear": a.get("function") or "*"})


@command(
    "canvas_toolbox",
    "The Toolbox: every Streamlit element and container with its properties; with element: its new cell's code",
    opt("app", "The app's id (with element)."),
    opt("element", "An element's id (slider, selectbox...): the cell a drop makes."),
)
def canvas_toolbox(a: dict[str, Any]) -> Any:
    if a.get("element"):
        if not a.get("app"):
            raise CommandError("Send app with element: the cell's names are free of that app's.")
        return api.call("POST", f"/streamlit/apps/{_q(a['app'])}/toolbox", {"element": a["element"]})
    return api.call("GET", "/streamlit/toolbox")


@command(
    "canvas_container",
    "Add a layout container to a page: columns, tabs, expander, container, form, sidebar or popover (blocks "
    "go inside with streamlit_block_change parent, slot)",
    req("app", "The app's id."),
    req("page", "The page's id."),
    req("kind", "columns, tabs, expander, container, form, sidebar or popover."),
    opt(
        "props",
        'Its properties (canvas_toolbox lists them): {"widths": [2, 1]}, {"label": "Details"}.',
        "json",
    ),
    opt("parent", "A container to put it inside."),
    opt("slot", "Which of that container's slots, from 0.", "int"),
    opt("row", "Its row, from 1.", "int"),
    opt("column", "The column it starts in, 1 to 12.", "int"),
    opt("w", "Its width in columns (default 12).", "int"),
)
def canvas_container(a: dict[str, Any]) -> Any:
    body = {
        k: a[k] for k in ("kind", "props", "parent", "slot", "row", "column", "w") if a.get(k) is not None
    }
    return api.call("POST", f"/streamlit/apps/{_q(a['app'])}/pages/{_q(a['page'])}/containers", body)


@command(
    "canvas_arrange",
    "Arrange several blocks as one change: left, right, centre, top, bottom, same_width, same_height, "
    "distribute; or reset (Reset layout)",
    req("app", "The app's id."),
    req("page", "The page's id."),
    req("how", "How (reset needs no blocks)."),
    opt("blocks", 'The blocks\' ids, the first the one the others follow: ["b1", "b2"].', "json"),
)
def canvas_arrange(a: dict[str, Any]) -> Any:
    body = {"how": a["how"]} | ({"blocks": a["blocks"]} if a.get("blocks") is not None else {})
    return api.call("POST", f"/streamlit/apps/{_q(a['app'])}/pages/{_q(a['page'])}/arrange", body)


@command(
    "canvas_outline",
    "The Document Outline: a page as a tree (containers, their slots, blocks) in reading order",
    req("app", "The app's id."),
    opt("page", "One page's id (default: every page)."),
)
def canvas_outline(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/streamlit/apps/{_q(a['app'])}/outline", params={"page": a.get("page")})


@command(
    "canvas_add",
    "Add a Toolbox element to the front canvas: a named cell in the app notebook and its block (as a drop)",
    req("element", "The element's id (canvas_toolbox lists them): slider, selectbox, bar_chart..."),
    opt("parent", "A container to put it inside."),
    opt("slot", "Which of that container's slots, from 0.", "int"),
    opt("row", "Its row, from 1.", "int"),
    opt("column", "The column it starts in, 1 to 12.", "int"),
)
def canvas_add(a: dict[str, Any]) -> Any:
    return _window(
        "canvas.add",
        {k: a[k] for k in ("element", "parent", "slot", "row", "column") if a.get(k) is not None},
    )


# Launch, build history and the Performance Analyzer (2026-11-19): every launch is a build in the project's
# builds/<app>/<n>/; the analyzer records only while it is attached.


@command(
    "app_launch",
    "Launch a Streamlit app (Visual Studio's F5): a new build in builds/<app>/<n>/, run in its own window",
    req("app", "The canvas's id (streamlit_apps lists them)."),
    opt("analyzer", "true: the Performance Analyzer records from its first load.", "bool"),
)
def app_launch(a: dict[str, Any]) -> Any:
    body = {"analyzer": True} if a.get("analyzer") else {}
    return api.call("POST", f"/streamlit/apps/{_q(a['app'])}/launch", body)


@command("app_stop", "Stop a launched Streamlit app", req("app", "The canvas's id."))
def app_stop(a: dict[str, Any]) -> Any:
    return api.call("DELETE", f"/streamlit/apps/{_q(a['app'])}/launch")


@command(
    "builds_list",
    "An app's builds, newest first: number, time, what changed in words, its result, saved analyzer sessions",
    req("app", "The canvas's id."),
    opt("build", "One build's number: its files (read-only).", "int"),
)
def builds_list(a: dict[str, Any]) -> Any:
    if a.get("build") is not None:
        return api.call("GET", f"/streamlit/apps/{_q(a['app'])}/builds/{int(a['build'])}")
    return api.call("GET", f"/streamlit/apps/{_q(a['app'])}/builds")


@command(
    "builds_compare",
    "Two builds' code file by file: changed, added, removed, each side's text",
    req("app", "The canvas's id."),
    req("a", "The first build's number.", "int"),
    req("b", "The second build's number.", "int"),
)
def builds_compare(a: dict[str, Any]) -> Any:
    return api.call(
        "GET", f"/streamlit/apps/{_q(a['app'])}/builds/compare", params={"a": a["a"], "b": a["b"]}
    )


@command(
    "build_relaunch",
    "Run an old build again, its code as it was built",
    req("app", "The canvas's id."),
    req("build", "The build's number.", "int"),
)
def build_relaunch(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/streamlit/apps/{_q(a['app'])}/builds/{int(a['build'])}/launch")


@command(
    "build_restore",
    "Restore a build's code into the app: its cells' code (undoable in their documents) and its layout",
    req("app", "The canvas's id."),
    req("build", "The build's number.", "int"),
)
def build_restore(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/streamlit/apps/{_q(a['app'])}/builds/{int(a['build'])}/restore")


@command(
    "perf_attach",
    "Attach the Performance Analyzer to a launched app (it records only while attached)",
    req("app", "The canvas's id (its launch must be running)."),
    opt("on", "false: pause; true (default): record.", "bool"),
    opt("clear", "true: start a new session.", "bool"),
    opt("detach", "true: detach (nothing more is recorded).", "bool"),
    opt("save", "true: save the session into its build (perf-<time>.json).", "bool"),
)
def perf_attach(a: dict[str, Any]) -> Any:
    path = f"/streamlit/apps/{_q(a['app'])}/perf"
    if a.get("detach"):
        return api.call("DELETE", path)
    if a.get("save"):
        return api.call("POST", f"/streamlit/apps/{_q(a['app'])}/perf/save")
    body = {k: a[k] for k in ("on", "clear") if a.get(k) is not None}
    return api.call("POST", path, body)


@command(
    "perf_session",
    "The analyzer's session: each rerun (trigger, each block's time), calls, caches, the web socket's messages",
    req("app", "The canvas's id."),
    opt("build", "A build's number, with `file`: a saved session.", "int"),
    opt("file", "A saved session's file (perf-<time>.json; builds_list names them)."),
)
def perf_session(a: dict[str, Any]) -> Any:
    if a.get("build") is not None and a.get("file"):
        return api.call(
            "GET", f"/streamlit/apps/{_q(a['app'])}/builds/{int(a['build'])}/perf/{_q(a['file'])}"
        )
    if a.get("build") is not None or a.get("file"):
        raise CommandError("A saved session takes both build and file.")
    return api.call("GET", f"/streamlit/apps/{_q(a['app'])}/perf")


@command(
    "perf_hints",
    "The analyzer's hints in plain words: what to change, and where",
    req("app", "The canvas's id."),
)
def perf_hints(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/streamlit/apps/{_q(a['app'])}/perf/hints")
