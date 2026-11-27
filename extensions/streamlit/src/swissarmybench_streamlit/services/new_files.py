"""New file's types a Streamlit project adds (the base's domain/new_files.py; the owner, 2026-11-27: "The list
of follow-ups available should change with projects"): a widget and a canvas, each made by this extension's
own "new" path (Widgets.new into the project's widgets/, Canvases.open with a name), never a second starter.

The two types are data in the extension's MODE (`new_files`: the base draws them, the page names neither).

makers   each type's maker for the base's hooks: ({name, folder, check}, who) -> {path, relative, address}
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote

from swissarmybench.services.workspace import Conflict
from swissarmybench_streamlit.domain import canvas_build as build_rules
from swissarmybench_streamlit.domain import canvas_model as model
from swissarmybench_streamlit.domain import widgets as widget_rules
from swissarmybench_streamlit.services.canvas import Canvases
from swissarmybench_streamlit.services.widgets import Widgets

WIDGET_ENDING = ".widget.py"

Maker = Callable[[dict[str, Any], str], Awaitable[dict[str, Any]]]


def _stem(name: Any, ending: str) -> str:
    text = str(name or "").strip()
    return text[: -len(ending)] if text.lower().endswith(ending) else text


def makers(
    widgets: Widgets, canvases: Canvases, project_folder: Callable[[], str | None]
) -> dict[str, Maker]:
    async def widget(body: dict[str, Any], who: str) -> dict[str, Any]:
        name = _stem(body.get("name"), WIDGET_ENDING)
        said = widget_rules.check_name(name, frozenset(widgets.names()))
        if not said["ok"]:
            raise Conflict(said["said"]) if said["state"] == "taken" else ValueError(said["said"])
        relative = f"widgets/{name}{WIDGET_ENDING}"
        folder = (project_folder() or "").replace("\\", "/").rstrip("/")
        made = {
            "path": f"{folder}/{relative}",
            "relative": relative,
            "address": f"widgets?name={quote(name)}",
        }
        if not body.get("check"):
            await widgets.new({"name": name, "where": "project"}, who)
        return made

    async def canvas(body: dict[str, Any], who: str) -> dict[str, Any]:
        name = _stem(body.get("name"), model.SUFFIX)
        folder = (project_folder() or "").replace("\\", "/").rstrip("/")
        if not folder:
            raise ValueError("Open a project first: a canvas is a file of its folder.")
        relative = f"{build_rules.slug(name)}{model.SUFFIX}"
        path = f"{folder}/{relative}"
        if canvases.exists(path):
            raise Conflict(f"{relative} is there already: pick another name.")
        if not body.get("check"):
            path = (await canvases.open({"name": name, "folder": folder}, who))["path"]
        return {"path": path, "relative": relative, "address": f"canvas?path={quote(path, safe='')}"}

    return {"widget": widget, "canvas": canvas}
