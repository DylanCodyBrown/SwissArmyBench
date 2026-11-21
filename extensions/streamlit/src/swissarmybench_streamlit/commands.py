"""The Streamlit extension's agent commands (the golden rule: every action on the Canvas and in the Widgets window
is one of these). The base's registry (swissarmybench/cli/commands.py) takes them when the extension is on, so
each is an MCP tool and a `sab` command too; with it off, a call says which extension it needs. Standard library
only (the `sab` command reads them).

A canvas (the owner, 2026-11-21) is a project's `<app>.canvas.json`: pages of containers placed in pixels, each
holding containers and widget instances. A widget is the library's `widgets/<name>.widget.py`. canvas_* change a
canvas as the user does (each change checked by the layout's rules and undoable); widgets_* work the widgets.
"""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.commands import Command, Registrar, _q, opt, req

COMMANDS: dict[str, Command] = {}


command = Registrar(COMMANDS)

# The app notebook, its old canvas (.stapp.json), its designer and its live cells went (the owner, 2026-11-21:
# "Creating a widget is what will replace the concept of app cells and app notebooks"): an old call says so.
GONE: dict[str, str] = {
    name: f"{name} went (2026-11-21): app notebooks and their canvases were replaced by widgets and the Canvas: "
    "widgets_* make and run widgets, canvas_* build a page of them."
    for name in [
        "A function's cache decorator in a cell's code: st.cache_data or st.cache_resource, its settings, or none",
        "A widget's event handler: a function stub in its cell and on_change= (or on_click=) set",
        "Install Streamlit into the app's Python (when streamlit_run says so)",
        "The front canvas: its app id (for streamlit_*), page, blocks or live page",
        "build_relaunch",
        "build_restore",
        "builds_compare",
        "canvas_add",
        "canvas_add_handler",
        "canvas_arrange",
        "canvas_bind",
        "canvas_cache_clear",
        "canvas_container",
        "canvas_inspect",
        "canvas_outline",
        "canvas_set_cache",
        "canvas_set_default",
        "canvas_set_property",
        "canvas_state_set",
        "canvas_table",
        "canvas_toolbox",
        "go inside with streamlit_block_change parent, slot)",
        "perf_attach",
        "perf_hints",
        "perf_session",
        "streamlit_address",
        "streamlit_app",
        "streamlit_apps",
        "streamlit_block_change",
        "streamlit_block_place",
        "streamlit_block_remove",
        "streamlit_cells",
        "streamlit_check",
        "streamlit_close",
        "streamlit_export",
        "streamlit_install",
        "streamlit_open",
        "streamlit_page_add",
        "streamlit_page_change",
        "streamlit_page_remove",
        "streamlit_page_settings",
        "streamlit_run",
        "streamlit_save",
        "streamlit_save_as",
        "streamlit_state",
        "streamlit_stop",
        "streamlit_test",
        "workbench_canvas",
        "workbench_canvas_edit",
        "workbench_canvas_move_to_data",
        "workbench_canvas_play",
        "workbench_live_cells",
        "workbench_live_resize",
        "workbench_live_run",
        "workbench_new_app",
    ]
}


def _command(canvas: str, kind: str, body: dict[str, Any]) -> Any:
    return api.call("POST", f"/streamlit/canvases/{_q(canvas)}/command", {"kind": kind, **body})


def _given(a: dict[str, Any], *names: str) -> dict[str, Any]:
    return {n: a[n] for n in names if a.get(n) is not None}


@command(
    "canvas_open",
    "Open a project's canvas (<app>.canvas.json) by its path, or make one by its name: its id, model, version",
    opt("path", "The canvas file's path."),
    opt("name", "A new canvas's name (in the open project's folder)."),
)
def canvas_open(a: dict[str, Any]) -> Any:
    return api.call("POST", "/streamlit/canvases", _given(a, "path", "name") | {"create": True})


@command(
    "canvas_list",
    "The open project's canvases (and old .stapp.json files, said)",
    opt("folder", "Another project folder."),
)
def canvas_list(a: dict[str, Any]) -> Any:
    return api.call("GET", "/streamlit/canvases" + (f"?folder={_q(a['folder'])}" if a.get("folder") else ""))


@command(
    "canvas_state",
    "A canvas: pages, containers, widget instances (px), version, missing widgets, marked values, notes",
    req("canvas", "The canvas's id (canvas_open gives it)."),
)
def canvas_state(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/streamlit/canvases/{_q(a['canvas'])}")


@command(
    "canvas_add_container",
    "Draw a container on a page or in a container (px of the layout's design width: desktop 1200, phone 390; "
    "without x and y: the first free place). The other layout places it by itself",
    req("canvas", "The canvas's id."),
    opt("page", "The page's id (default: the first)."),
    opt("parent", "A container's id to nest it in."),
    opt("x", "Left, px.", "int"),
    opt("y", "Top, px.", "int"),
    opt("w", "Width, px.", "int"),
    opt("h", "Height, px.", "int"),
    opt(
        "props",
        "title, border, padding, height (fit, fixed), scrollable, resizable, background, columns.",
        "json",
    ),
    opt("layout", "desktop (default) or phone: whose places these are."),
)
def canvas_add_container(a: dict[str, Any]) -> Any:
    return _command(
        a["canvas"], "add_container", _given(a, "page", "parent", "x", "y", "w", "h", "props", "layout")
    )


@command(
    "canvas_insert_widget",
    "Insert a widget into a container (no container: one is made around it); its values override its defaults",
    req("canvas", "The canvas's id."),
    req("widget", "The widget's name (widgets_list)."),
    opt("parent", "The container's id."),
    opt("page", "The page's id."),
    opt("x", "Left in the container, px.", "int"),
    opt("y", "Top in the container, px.", "int"),
    opt("values", "Property values (JSON object).", "json"),
    opt("layout", "desktop (default) or phone: whose places these are."),
)
def canvas_insert_widget(a: dict[str, Any]) -> Any:
    return _command(
        a["canvas"], "insert_widget", _given(a, "widget", "parent", "page", "x", "y", "values", "layout")
    )


@command(
    "canvas_move",
    "Move or resize a container or widget (px), or put it in another container (parent; empty: the page)",
    req("canvas", "The canvas's id."),
    req("id", "The container's or widget's id."),
    opt("x", "Left, px.", "int"),
    opt("y", "Top, px.", "int"),
    opt("w", "Width, px.", "int"),
    opt("h", "Height, px.", "int"),
    opt("parent", "A container's id; empty for the page."),
    opt("layout", "desktop (default) or phone: whose places these are."),
)
def canvas_move(a: dict[str, Any]) -> Any:
    body = _given(a, "id", "x", "y", "w", "h", "layout")
    if "parent" in a and a["parent"] is not None:
        body["parent"] = a["parent"]
    return _command(a["canvas"], "move", body)


@command(
    "canvas_set_container",
    "A container's properties: title, border, padding, height (fit, fixed), scrollable, resizable, background, "
    "columns",
    req("canvas", "The canvas's id."),
    req("id", "The container's id."),
    req("props", "The properties to set (JSON object).", "json"),
)
def canvas_set_container(a: dict[str, Any]) -> Any:
    return _command(a["canvas"], "set_container", {"id": a["id"], "props": a["props"]})


@command(
    "canvas_show",
    "Show a container or widget in both layouts, or in only one (desktop or phone)",
    req("canvas", "The canvas's id."),
    req("id", "The container's or widget's id."),
    req("show", "both, desktop or phone."),
)
def canvas_show(a: dict[str, Any]) -> Any:
    return _command(a["canvas"], "show", {"id": a["id"], "show": a["show"]})


@command(
    "canvas_set_values",
    "A widget instance's property values (null: back to the widget's default)",
    req("canvas", "The canvas's id."),
    req("id", "The instance's id."),
    req("values", "Property values (JSON object).", "json"),
)
def canvas_set_values(a: dict[str, Any]) -> Any:
    return _command(a["canvas"], "set_values", {"id": a["id"], "values": a["values"]})


@command(
    "canvas_replace_widget",
    "An instance's widget replaced (a missing one's Replace): its place kept",
    req("canvas", "The canvas's id."),
    req("id", "The instance's id."),
    req("widget", "The new widget's name."),
)
def canvas_replace_widget(a: dict[str, Any]) -> Any:
    return _command(a["canvas"], "replace_widget", {"id": a["id"], "widget": a["widget"]})


@command(
    "canvas_delete",
    "Delete a container (with what it holds) or a widget instance (undoable)",
    req("canvas", "The canvas's id."),
    req("id", "The container's or instance's id."),
)
def canvas_delete(a: dict[str, Any]) -> Any:
    return _command(a["canvas"], "delete", {"id": a["id"]})


@command(
    "canvas_set",
    "The canvas's sizing, shared by both layouts: columns (a guide), row_height, gap, snap, step (1, 2, 4, 8, grid)",
    req("canvas", "The canvas's id."),
    opt("columns", "Columns, 1 to 48.", "int"),
    opt("row_height", "Row height, px.", "int"),
    opt("gap", "Gap, px.", "int"),
    opt("snap", "Snap on or off.", "bool"),
    opt("step", "1, 2, 4, 8 or grid.", "any"),
)
def canvas_set(a: dict[str, Any]) -> Any:
    return _command(a["canvas"], "sizing", _given(a, "columns", "row_height", "gap", "snap", "step"))


@command(
    "canvas_page",
    "A canvas's pages: add one (no page), rename one (name), move one (index), or remove one (remove)",
    req("canvas", "The canvas's id."),
    opt("page", "The page's id."),
    opt("name", "Its name."),
    opt("index", "Its new place, from 0.", "int"),
    opt("remove", "true: remove the page.", "bool"),
)
def canvas_page(a: dict[str, Any]) -> Any:
    if not a.get("page"):
        return _command(a["canvas"], "add_page", _given(a, "name"))
    if a.get("remove"):
        return _command(a["canvas"], "remove_page", {"page": a["page"]})
    return _command(a["canvas"], "change_page", _given(a, "page", "name", "index"))


@command("canvas_undo", "Undo the canvas's last change", req("canvas", "The canvas's id."))
def canvas_undo(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/streamlit/canvases/{_q(a['canvas'])}/undo", {})


@command("canvas_redo", "Redo the canvas's change undone last", req("canvas", "The canvas's id."))
def canvas_redo(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/streamlit/canvases/{_q(a['canvas'])}/redo", {})


@command(
    "canvas_play",
    "Play a canvas: its pages built and run live (its address); with check: every page headless, each widget's "
    "errors",
    req("canvas", "The canvas's id."),
    opt("page", "The page's id to show."),
    opt("check", "true: run headless (AppTest) and say each page's errors.", "bool"),
)
def canvas_play(a: dict[str, Any]) -> Any:
    if a.get("check"):
        return api.call("POST", f"/streamlit/canvases/{_q(a['canvas'])}/check", {})
    return api.call("POST", f"/streamlit/canvases/{_q(a['canvas'])}/play", _given(a, "page"))


@command(
    "canvas_stop",
    "Stop a canvas's Play (run play, the default) or its launched app (run launch)",
    req("canvas", "The canvas's id."),
    opt("run", "play or launch."),
)
def canvas_stop(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/streamlit/canvases/{_q(a['canvas'])}/stop", _given(a, "run"))


@command(
    "canvas_export",
    "Export a canvas as an app that runs alone on a hosted Streamlit app (app.py, pages, the widgets inlined, the "
    "tables' rows as Parquet). Waits for the user's Allow; declined, nothing is written",
    req("canvas", "The canvas's id."),
    req("folder", "Where it goes."),
)
def canvas_export(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/streamlit/canvases/{_q(a['canvas'])}/export", {"folder": a["folder"]})


@command(
    "app_launch",
    "Launch a canvas (Visual Studio's F5): a new build in builds/<app>/<n>/, run in its own window",
    req("canvas", "The canvas's id."),
)
def app_launch(a: dict[str, Any]) -> Any:
    return api.call("POST", f"/streamlit/canvases/{_q(a['canvas'])}/launch", {})


# ===== widgets (the owner, 2026-11-21: a widget replaces app cells and app notebooks) =====


@command(
    "widgets_list",
    "Every widget of the canvas's framework: the library's, then the prebuilt ones (read-only), with their "
    "properties (name, type, mask, default)",
    opt("q", "Words to search names, descriptions, groups and tags."),
)
def widgets_list(a: dict[str, Any]) -> Any:
    return api.call("GET", "/streamlit/widgets" + (f"?q={_q(a['q'])}" if a.get("q") else ""))


@command(
    "widgets_get", "One widget: its header, code, properties and file", req("name", "The widget's name.")
)
def widgets_get(a: dict[str, Any]) -> Any:
    return api.call("GET", f"/streamlit/widgets/{_q(a['name'])}")


@command(
    "widgets_new",
    "A new widget in the library (widgets/<name>.widget.py); top-level plain values in its code are its properties",
    opt("name", "Small letters, digits and _ (default: a free one)."),
    opt("description", "One line."),
    opt("code", "Its Streamlit code (default: a starting template)."),
)
def widgets_new(a: dict[str, Any]) -> Any:
    return api.call(
        "POST", "/streamlit/widgets", {k: a[k] for k in ("name", "description", "code") if a.get(k)}
    )


@command(
    "widgets_save",
    "Save a widget's code (below its header; the header is kept)",
    req("name", "The widget's name."),
    req("code", "Its whole code."),
)
def widgets_save(a: dict[str, Any]) -> Any:
    return api.call("PUT", f"/streamlit/widgets/{_q(a['name'])}", {"code": a["code"]})


@command(
    "widgets_header",
    "A widget's name, description, group or size, written into its file's header only; a new name renames every "
    "canvas instance",
    req("name", "The widget's present name."),
    opt("new_name", "Its new name."),
    opt("description", "Its new description."),
    opt("group", "Buttons, Inputs, Data, Charts, Text, Filters, Forms or Other."),
)
def widgets_header(a: dict[str, Any]) -> Any:
    body = {k: a[k] for k in ("description", "group") if a.get(k) is not None}
    if a.get("new_name"):
        body["name"] = a["new_name"]
    return api.call("PATCH", f"/streamlit/widgets/{_q(a['name'])}", body)


@command(
    "widgets_properties",
    "A widget's properties (each with its type and mask), or those of code not saved yet",
    opt("name", "The widget's name."),
    opt("code", "Code to read instead."),
)
def widgets_properties(a: dict[str, Any]) -> Any:
    return api.call("POST", "/streamlit/widgets/properties", {k: a[k] for k in ("name", "code") if a.get(k)})


@command(
    "widgets_set_property",
    "A property's default, written into only its own characters in the widget's code (checked first)",
    req("name", "The widget's name."),
    req("property", "The property."),
    req("value", "Its new value (JSON: a string, a number, true...).", "any"),
)
def widgets_set_property(a: dict[str, Any]) -> Any:
    return api.call(
        "POST",
        f"/streamlit/widgets/{_q(a['name'])}/property",
        {"property": a["property"], "value": a["value"]},
    )


@command(
    "widgets_run",
    "Run a widget alone, headless (AppTest): what it drew, its errors (each failing widget's own panel), its "
    "address when live is true",
    req("name", "The widget's name."),
    opt("values", "Property values to run it with (JSON object).", "json"),
    opt("live", "Also run it as a live page and give its address.", "bool"),
)
def widgets_run(a: dict[str, Any]) -> Any:
    body = {"values": a.get("values") or {}}
    checked = api.call("POST", f"/streamlit/widgets/{_q(a['name'])}/check", body)
    if a.get("live"):
        checked["live"] = api.call(
            "POST", f"/streamlit/widgets/{_q(a['name'])}/run", body | {"window": "agent"}
        )
    return checked


@command(
    "widgets_copy",
    "Copy a widget (a prebuilt one) into the library as your own",
    req("name", "The widget to copy."),
    opt("new_name", "The copy's name (default: my_<name>)."),
)
def widgets_copy(a: dict[str, Any]) -> Any:
    return api.call(
        "POST",
        f"/streamlit/widgets/{_q(a['name'])}/copy",
        {"name": a["new_name"]} if a.get("new_name") else {},
    )


@command(
    "widgets_delete",
    "Delete a widget from the library. Waits for the user's Allow; declined, nothing is deleted",
    req("name", "The widget's name."),
)
def widgets_delete(a: dict[str, Any]) -> Any:
    return api.call("DELETE", f"/streamlit/widgets/{_q(a['name'])}")


@command(
    "widgets_preview",
    "A widget's small rendered preview (PNG): its state (ready with its address, coming, failed with why)",
    req("name", "The widget's name."),
    opt("theme", "light or dark."),
)
def widgets_preview(a: dict[str, Any]) -> Any:
    return api.call(
        "GET", f"/streamlit/widgets/{_q(a['name'])}/preview?theme={_q(a.get('theme') or 'light')}"
    )
