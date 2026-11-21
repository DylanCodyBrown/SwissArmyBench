"""The Streamlit extension as the base reads it (swissarmybench/extensions.py; its entry point:
`streamlit = "swissarmybench_streamlit.extension"` in the group `swissarmybench.extensions`). Preinstalled:
the installers and each update install it beside the base; Remove on the Extensions page takes it away, and
the app is the BI base without it (no Apps area, no Streamlit canvas; its tools say which extension they
need).

  ID, NAME, DESCRIPTION, ADDS   the extension, said for the Extensions page and context.md
  PROJECT_TYPE, MODE            the Streamlit project and its mode, as DATA (Plans/editions.plan.md, "Project
                                modes"): the Streamlit canvas, the Streamlit, Components, Controllers and Text
                                and layout families, Python, the agent's tool group, the export
  BASE_MODE_ADDS                what it adds to the base's own mode while it is on: today's app offers the
                                Streamlit canvas in every BI project, as it did before it was an extension
  FRONT_END                     the front-end plug-ins it names (they live in the shared web/)
  AREAS, commands()             its agent commands (commands.py) and their areas, added to the base's registry
  STARTERS                      its starter families (starters/*.blade.py), beside the base's
  SECRET_PATHS, SESSION_RULES   its live pages' secret path, its Session page words
  routes(services)              its routes, its services built from the base's (this is its composition root);
                                it fills the base's hooks (services/hooks.py): the documents the windows hold,
                                a canvas, what stops with a kernel or a window, an app's own file
  stop(services)                its Streamlit processes and their temporary folders, when the server stops
  scaffold(name, data_names)    a Streamlit project's own files: app.ipynb and the app's canvas
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from swissarmybench_streamlit import __version__

ID = "streamlit"
NAME = "Streamlit"
VERSION = __version__
DESCRIPTION = "Build Streamlit apps from your notebooks' cells."
ADDS = [
    "The Apps area and the Streamlit canvas: pages of blocks, each a link to a cell",
    "Live cells: a Python cell that calls Streamlit shows its page in place",
    "App mode: page settings, the live page's state, controllers and Test this page",
    "Export (an app that runs alone) and Save as (the project's pages/*.py)",
    "The Streamlit, Components, Controllers and Text and layout starters",
]
PACKAGE = "swissarmybench-streamlit"
PROJECT_TYPE = "streamlit"
# The front-end plug-ins it names (in the shared web/: the canvas, live cells, App mode's panels).
FRONT_END = ["streamlit-canvas", "live-cells"]
# Its commands' area (cli/commands.py AREAS: the prefix, then what it works on).
AREAS = (
    ("streamlit", "Streamlit: an app's canvas (pages of blocks linked to cells), Play, export, Save as"),
    ("canvas", "The canvas's designer: the property pane (uses, state, cache), Toolbox, containers, events"),
    ("builds", "Builds: every launch of an app, kept in its project's builds/ (list, compare)"),
    ("build", "One build: run it again, restore its code into the app"),
    ("perf", "The Performance Analyzer: a launched app's reruns, calls, caches, web socket, hints"),
    (
        "widgets",
        "Widgets: the library's and the prebuilt ones, their properties (types, masks), run alone, previews",
    ),
)
FAMILIES = ["Streamlit", "Components", "Controllers", "Text and layout"]
MODE: dict[str, Any] = {
    "type": PROJECT_TYPE,
    "name": NAME,
    "deliverable": "a Streamlit app",
    "canvases": ["streamlit"],
    "families": FAMILIES,
    "languages": ["python"],
    "cell_kinds": [],
    "tools": ["streamlit_"],
    "export": ["app", "pages"],
    # For a beginner choosing a project type (New project).
    "title": "Streamlit app",
    "for_whom": "Anyone who wants a small web app on their data, for themselves or their team.",
    "explain": (
        "Your notebook's cells become an app: drag a cell onto a page, and its chart, table or filter shows "
        "there. A filter on one block drives every block that reads its value."
    ),
    "example": "A sales dashboard with a region filter, a chart by month and a table of the top customers.",
}
# The base's own mode while this is on: today's app offers the Streamlit canvas in a BI project too.
BASE_MODE_ADDS: dict[str, list[str]] = {"canvases": ["streamlit"]}

STARTERS = str(Path(__file__).resolve().parent / "starters")
LIVE_PREFIX = "/streamlit/live/"
LIVE_RUN = "/streamlit/run/"  # a widget run alone and a canvas's Play (services/widgets.py LiveRuns)
SECRET_PATHS = (LIVE_PREFIX, LIVE_RUN)
SESSION_RULES: dict[str, Any] = {}  # its words are the base's today (domain/session_log.py's app rules)


def describe() -> dict[str, Any]:
    """What its entry point gives: the extension as the Extensions page shows it, and its mode."""
    return {
        "id": ID,
        "name": NAME,
        "description": DESCRIPTION,
        "version": VERSION,
        "adds": list(ADDS),
        "package": PACKAGE,
        "project_type": PROJECT_TYPE,
        "mode": dict(MODE),
        "front_end": list(FRONT_END),
    }


def routes(services: Any) -> list[Any]:
    """Its routes, its services built from the base's (bootstrap's Services), and the base's hooks filled."""
    from swissarmybench.server import streamlit_proxy
    from swissarmybench_streamlit.adapters.streamlit_files import AppFiles
    from swissarmybench_streamlit.domain import streamlit_cells
    from swissarmybench_streamlit.server import routes_canvas, routes_controllers, routes_streamlit
    from swissarmybench_streamlit.server.streamlit_apps import Runner
    from swissarmybench_streamlit.services.canvas_pane import CanvasPane
    from swissarmybench_streamlit.services.controllers import Controllers
    from swissarmybench_streamlit.services.streamlit import StreamlitApps
    from swissarmybench_streamlit.services.streamlit_documents import AppFile

    # A canvas's pages and a document's live cells, written to a temporary folder of the app's own and run
    # in the document's own Python (Streamlit is never this app's dependency).
    app_files = AppFiles()
    runner = Runner(report=lambda *e: services.process_event("streamlit", *e))
    documents = services.documents
    apps = StreamlitApps(
        services.ws,
        app_files,
        runner,
        services.export_writer,
        now=time.time,
        read_document=documents.read,
        environment_of=documents.environment,
        project_files=services.project_files,
        table_cells=services.table_cells.group_cells,
        arrange=services.table_cells.arrange,
        approvals=services.agent.approvals,
        data_export=services.data_export,
        local_notes=services.script_exports.local_notes,
        query_module=services.script_exports.query_module,
    )
    # A canvas page's controllers: its check, Test this page (AppTest in the app's Python), thin cells.
    controllers = Controllers(apps, app_files, runner, services.project_files)
    # The property pane and the designer (the owner, 2026-11-19): what a block uses, its state and cache.
    pane = CanvasPane(
        apps,
        variables=getattr(getattr(services, "variables", None), "listing", None),
        lineage=getattr(getattr(services, "lineage", None), "trace", None),
        is_set=lambda name: name in os.environ,
        places=getattr(getattr(services, "catalogs", None), "places", None),
    )
    services.canvas_pane = pane
    services.streamlit = apps  # its stop, and tests
    # Launch, builds and the Performance Analyzer (2026-11-19): builds/ in the project, a run of its own.
    from swissarmybench.settings import Settings
    from swissarmybench_streamlit.adapters.build_files import BuildFiles
    from swissarmybench_streamlit.server import routes_launch
    from swissarmybench_streamlit.services.launch import LAUNCH_PATH, Launches

    launches = Launches(apps, app_files, BuildFiles(), runner, services.project_files)
    services.launches = launches
    services.controllers = controllers

    # Widgets (the owner, 2026-11-21): the library's widgets/ and the prebuilt ones, run alone or on a canvas.
    from swissarmybench_streamlit.adapters.widget_files import PreviewFiles, WidgetFiles
    from swissarmybench_streamlit.server import routes_widgets
    from swissarmybench_streamlit.server.live_runs import LiveRuns
    from swissarmybench_streamlit.services.widgets import Widgets

    library = getattr(services, "library", None)
    widget_files = WidgetFiles(
        library.folder if library is not None else None,
        made=library.made if library is not None else (lambda: None),
    )
    live_runs = LiveRuns(app_files, runner)
    settings = getattr(services, "settings", None)
    state_dir = getattr(settings, "state_dir", None)
    preview_files = PreviewFiles(Path(state_dir) / "widget-previews" if state_dir else None)

    def open_tables() -> dict[str, list[str] | None]:
        from swissarmybench.domain.codegen import variable_name

        found: dict[str, list[str] | None] = {}
        for info in services.ws.store.all():
            if services.ws.grids.first_for(info.name) is not None:
                found.setdefault(variable_name(info.name), [c.name for c in info.columns])
        return found

    def project_python() -> str | None:
        project = (
            (services.sab_projects.state().get("project") or {}) if hasattr(services, "sab_projects") else {}
        )
        folder = project.get("folder")
        if not folder:
            return None
        try:
            return documents.environment(str(Path(folder) / "data.ipynb"))  # type: ignore[no-any-return]
        except Exception:
            return None

    widgets = Widgets(
        services.ws,
        widget_files,
        live_runs,
        services.agent.approvals,
        tables=open_tables,
        table_data=apps.table_data,
        project_python=project_python,
        previews=preview_files,
        variables=lambda: set(os.environ),
    )
    services.widgets = widgets
    services.live_runs = live_runs

    hooks = services.hooks
    hooks.documents = apps.documents
    hooks.unsaved = apps.unsaved
    hooks.held = apps.held
    hooks.canvas = apps.canvas
    hooks.read_trace = app_files.read_trace
    hooks.kernel_stopped = apps.kernel_stopped
    hooks.stop_orphans = apps.stop_orphans
    hooks.canvas_references = streamlit_cells.canvas_references
    hooks.app_document = AppFile()
    hooks.live_cells = streamlit_cells.live_cells
    hooks.project_app = project_app
    hooks.app_pages = streamlit_cells.outline_pages
    return [
        *routes_widgets.routes(widgets, None, getattr(settings, "web_root", Settings().web_root)),
        *streamlit_proxy.routes(live_runs.port_of, prefix=LIVE_RUN, what="This widget or canvas"),
        *routes_streamlit.routes(apps),
        *routes_controllers.routes(controllers),
        *routes_canvas.routes(pane, apps),
        *routes_launch.routes(
            launches, getattr(getattr(services, "settings", None), "web_root", Settings().web_root)
        ),
        *streamlit_proxy.routes(apps.port_of),
        *streamlit_proxy.routes(
            launches.port_of, prefix=LAUNCH_PATH, what="This launched app", tap=launches.tap
        ),
    ]


async def stop(services: Any) -> None:
    """When the server stops: no Streamlit process outlives it, nor its temporary folder."""
    launches = getattr(services, "launches", None)
    if launches is not None:
        await launches.stop_all()
    live_runs = getattr(services, "live_runs", None)
    if live_runs is not None:
        await live_runs.stop_all()
    apps = getattr(services, "streamlit", None)
    if apps is not None:
        await apps.stop_all()


def project_app(name: str) -> dict[str, Any]:
    """A new project's app (the base's BI project, as before this was an extension): an empty canvas named
    after the project, and Streamlit in its requirements."""
    from swissarmybench_streamlit.domain import streamlit_cells

    canvas = f"{streamlit_cells.slug(name)}{streamlit_cells.APP_SUFFIX}"
    return {"files": {canvas: streamlit_cells.write_app([])}, "requirements": ["streamlit>=1.36"]}


def scaffold(name: str, data_names: list[str]) -> dict[str, Any]:
    """A Streamlit project's own files (beside data.ipynb and data.py): app.ipynb, the app notebook its
    blocks' cells go in (starting from data.py's names), and the app's canvas."""
    from swissarmybench.domain import notebooks

    first = f"from data import {', '.join(data_names)}" if data_names else "import data"
    made = project_app(name)
    files = {"app.ipynb": notebooks.write_notebook([notebooks.Cell("code", first)]), **made["files"]}
    return {"app": False, "files": files, "requirements": list(made["requirements"])}


def commands() -> dict[str, Any]:
    """Its agent commands, for the base's registry (cli/commands.py adds them when this is on)."""
    from swissarmybench_streamlit.commands import COMMANDS

    return COMMANDS
