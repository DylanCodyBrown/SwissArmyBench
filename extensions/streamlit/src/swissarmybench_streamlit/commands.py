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

from collections.abc import Callable
from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.commands import Arg, Command, CommandError, _q, _window, opt, req

COMMANDS: dict[str, Command] = {}
Run = Callable[[dict[str, Any]], Any]


def command(name: str, summary: str, *args: Arg) -> Callable[[Run], Run]:
    def register(run: Run) -> Run:
        COMMANDS[name] = Command(name, summary, args, run, False, False)
        return run

    return register


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
)
def streamlit_block_change(a: dict[str, Any]) -> Any:
    body: dict[str, Any] = {k: a[k] for k in ("row", "column", "insert", "w") if a.get(k) is not None}
    if a.get("h") is not None:
        body["h"] = a["h"] or None
    if a.get("to_page"):
        body["page"] = a["to_page"]
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
