"""The Streamlit extension as the base reads it (swissarmybench/extensions.py; its entry point:
`streamlit = "swissarmybench_streamlit.extension"` in the group `swissarmybench.extensions`). Preinstalled:
the installers and each update install it beside the base; Remove on the Extensions page takes it away, and
the app is the BI base without it (no Canvas, no Widgets; its tools say which extension they need).

  ID, NAME, DESCRIPTION, ADDS   the extension, said for the Extensions page and context.md
  PROJECT_TYPE, MODE            the Streamlit project and its mode, as DATA (Plans/editions.plan.md, "Project
                                modes"): the Streamlit canvas, its widgets' framework, Python, the
                                agent's tool groups, the export
  BASE_MODE_ADDS                what it adds to the base's own mode while it is on: today's app offers the
                                Streamlit canvas in every BI project, as it did before it was an extension
  FRONT_END                     the front-end plug-ins it names (they live in the shared web/)
  AREAS, commands()             its agent commands (commands.py) and their areas, added to the base's registry
  STARTERS                      its starter families (starters/*.blade.py: snippets for a widget's code)
  SECRET_PATHS, SESSION_RULES   its live pages' secret path, its Session page words
  routes(services)              its routes, its services built from the base's (this is its composition root);
                                it fills the base's hooks (services/hooks.py): an old app file said, a new
                                project's canvas
  stop(services)                its Streamlit processes and their temporary folders, when the server stops
  scaffold(name, data_names)    a Streamlit project's own files: an empty canvas
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from swissarmybench_streamlit import __version__

ID = "streamlit"
NAME = "Streamlit"
VERSION = __version__
DESCRIPTION = "Build Streamlit apps from widgets on a canvas."
ADDS = [
    "Widgets: your own in the library and 60 prebuilt ones (four call the local sandbox API)",
    "The Widgets window: write a widget with completion and help, Run it in place",
    "The Canvas: draw containers, insert widgets, set their properties; Play, Launch, Export",
]
PACKAGE = "swissarmybench-streamlit"
PROJECT_TYPE = "streamlit"
# The front-end plug-ins it names (in the shared web/: the Canvas page, the Widgets window).
FRONT_END = ["streamlit-canvas", "widgets"]
# Its commands' area (cli/commands.py AREAS: the prefix, then what it works on).
AREAS = (
    ("canvas", "The Canvas: pages of containers and widget instances in px, sizing, snap, Play, Export"),
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
    "tools": ["canvas_", "widgets_"],
    # The app framework its canvas uses: the Widgets browser and the canvas show that framework's widgets.
    "widget_framework": "streamlit",
    "export": ["app", "pages"],
    # For a beginner choosing a project type (New project).
    "title": "Streamlit app",
    "for_whom": "Anyone who wants a small web app on their data, for themselves or their team.",
    "explain": (
        "Draw containers on a canvas and insert widgets: charts, tables, filters and buttons, each with its "
        "properties. A filter widget sets a value the other widgets read."
    ),
    "example": "A sales dashboard with a region filter, a chart by month and a table of the top customers.",
}
# The base's own mode while this is on: today's app offers the Streamlit canvas in a BI project too.
BASE_MODE_ADDS: dict[str, list[str]] = {"canvases": ["streamlit"]}

STARTERS = str(Path(__file__).resolve().parent / "starters")
LIVE_RUN = "/streamlit/run/"  # a widget run alone and a canvas's Play (server/live_runs.py LiveRuns)
SECRET_PATHS = (LIVE_RUN,)
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
    from swissarmybench.services.ports import BACKGROUND
    from swissarmybench.settings import Settings
    from swissarmybench_streamlit.adapters.build_files import BuildFiles
    from swissarmybench_streamlit.adapters.streamlit_files import AppFiles, parquet_of
    from swissarmybench_streamlit.adapters.widget_files import (
        CanvasFiles,
        PreviewFiles,
        WidgetFiles,
        folder_names,
        read_text,
    )
    from swissarmybench_streamlit.server import routes_canvases, routes_launch, routes_widgets
    from swissarmybench_streamlit.server.live_runs import LiveRuns
    from swissarmybench_streamlit.server.previews import Previewer
    from swissarmybench_streamlit.server.streamlit_apps import Runner
    from swissarmybench_streamlit.services.canvas import Canvases
    from swissarmybench_streamlit.services.launch import Launches
    from swissarmybench_streamlit.services.open_tables import OpenTables
    from swissarmybench_streamlit.services.widgets import Widgets

    # A widget run alone and a canvas's Play: written to a temporary folder of the app's own and run in the
    # project's Python (Streamlit is never this app's dependency), passed through at /streamlit/run/.
    app_files = AppFiles()
    runner = Runner(report=lambda *e: services.process_event("streamlit", *e))
    live_runs = LiveRuns(app_files, runner)
    settings = getattr(services, "settings", None) or Settings()
    library = getattr(services, "library", None)
    documents = services.documents

    def project_folder() -> str | None:
        projects = getattr(services, "sab_projects", None)
        project = (projects.state().get("project") or {}) if projects is not None else {}
        folder = project.get("folder")
        return str(folder) if folder else None

    def variable_names() -> list[str]:
        listing = getattr(getattr(services, "variables", None), "listing", None)
        found = (listing().get("variables") or []) if listing else []
        return [str(v.get("name")) for v in found if isinstance(v, dict) and v.get("name")]

    def project_python() -> str | None:
        folder = project_folder()
        if not folder:
            return None
        try:
            return documents.environment(str(Path(folder) / "data.ipynb"))  # type: ignore[no-any-return]
        except Exception:
            return None

    tables = OpenTables(services.ws, services.export_writer)
    # A table property also takes data.ipynb's tables (data.py's names) and a connection's [Conn].table,
    # read through the connection-tables contract: the one gate, so each connection's query limit holds.
    from swissarmybench_streamlit.domain.widget_properties import module_tables

    connection_tables = getattr(services, "connection_tables", None)

    def data_tables() -> list[str]:
        folder = project_folder()
        return module_tables(read_text(str(Path(folder) / "data.py"))) if folder else []

    def connection_names() -> set[str]:
        return set(connection_tables.names()) if connection_tables is not None else set()

    async def connection_listing() -> dict[str, list[str] | None]:
        out: dict[str, list[str] | None] = {}
        if connection_tables is None:
            return out
        for name in connection_tables.names():
            try:
                saved, kind = connection_tables.kind(name)
                if (
                    kind == "sandbox"
                ):  # the project's sandbox: its made-up copies, listed now (never live data)
                    out[saved] = sorted(f"[{saved}].{p.table}" for p in await connection_tables.places(saved))
                    continue
                out[name] = await connection_tables.listed(name)
            except Exception:  # noqa: S112 (a key vault, a kind with no tables: not offered)
                continue
        return out

    async def read_connection_table(reference: str) -> bytes:
        if connection_tables is None:
            raise LookupError("Connections are not here.")
        table = await connection_tables.read_named(reference)
        found: bytes = await services.ws.workers.run(BACKGROUND, parquet_of, table)
        return found

    widgets = Widgets(
        services.ws,
        WidgetFiles(
            library.folder if library is not None else None,
            made=library.made if library else lambda: None,
            project=project_folder,
        ),
        live_runs,
        services.agent.approvals,
        tables=tables.columns,
        table_data=tables.data,
        project_python=project_python,
        previews=PreviewFiles(Path(settings.state_dir) / "widget-previews"),
        variables=lambda: set(os.environ),
        variable_names=variable_names,
        project_folder=project_folder,
        data_tables=data_tables,
        connections=connection_names,
        connection_listing=connection_listing,
        read_connection_table=read_connection_table,
    )
    # An endpoint property's picker: the project's local sandbox API (the base's API.py), when it is there.
    local_api = getattr(services, "local_api", None)
    if local_api is not None:
        widgets.endpoints = local_api.endpoint_names
        widgets.endpoint_fields = local_api.endpoint_fields

        def api_uses() -> list[dict[str, Any]]:
            """Each canvas widget instance whose endpoint property names one of API.py's, and each Event
            wired to call one (Payload shapes)."""
            from swissarmybench_streamlit.domain import canvas_model

            folder = project_folder()
            if folder is None:
                return []
            out: list[dict[str, Any]] = []
            for file in sorted(Path(folder).glob("*.canvas.json")):
                try:
                    canvas = json.loads(file.read_text(encoding="utf-8"))
                    nodes = list(canvas_model.walk(canvas))
                except (OSError, ValueError, KeyError, TypeError):
                    continue
                for page, node in nodes:
                    values = node.get("values") or {}
                    if node.get("kind") == "widget" and values.get("endpoint"):
                        out.append(
                            {"canvas": file.name, "page": page.get("name"), "instance": node.get("id"),
                             "widget": node.get("widget"), "values": values}
                        )  # fmt: skip
                    for port, wire in (
                        (node.get("wires") or {}).items() if node.get("kind") == "widget" else ()
                    ):
                        actions = wire.get("actions") if isinstance(wire, dict) else None
                        for action in actions if isinstance(actions, list) else ():
                            if isinstance(action, dict) and action.get("do") == "call":
                                out.append(
                                    {"canvas": file.name, "page": page.get("name"),
                                     "instance": node.get("id"), "widget": node.get("widget"),
                                     "event": port, "action": action}
                                )  # fmt: skip
            return out

        local_api.api_uses = api_uses
    # The Canvas: the project's <app>.canvas.json files, every change rule-checked, kept and undoable.
    canvases = Canvases(
        services.ws,
        CanvasFiles(),
        widgets,
        live_runs,
        services.agent.approvals,
        app_files,
        project_folder=project_folder,
        read_data_py=lambda folder: read_text(str(Path(folder) / "data.py")),
        list_folder=folder_names,
        real_path=lambda path: os.path.realpath(os.path.expanduser(path)),
        builds=BuildFiles(),
    )
    # Launch, Builds and the Performance Analyzer (Visual Studio's F5, its history, its profiler).
    launches = Launches(canvases, live_runs, BuildFiles())
    canvases.launches = launches
    # Each widget's preview, rendered headless once (Play's own builder and run) and kept by its hash.
    previewer = Previewer(widgets, live_runs)
    services.widgets = widgets
    services.canvases = canvases
    services.launches = launches
    services.live_runs = live_runs
    services.previewer = previewer

    hooks = services.hooks
    hooks.app_document = GoneApp()  # an old .stapp.json: said in one line
    hooks.project_app = project_app
    hooks.app_pages = canvas_pages
    web_root = getattr(settings, "web_root", Settings().web_root)
    # Share… (the base's services/sharing.py): a launched canvas app's own port, tunnelled to the organization
    from swissarmybench_streamlit.services import sharing_target

    services.share_target = sharing_target.wire(services, live_runs, runner, canvases.title_of)
    return [
        *routes_widgets.routes(widgets, previewer, web_root),
        *routes_canvases.routes(canvases, web_root),
        *routes_launch.routes(launches, web_root),
        # The analyzer's tap: each websocket message of a launched app it records (its kind and size only).
        *streamlit_proxy.routes(
            live_runs.port_of, prefix=LIVE_RUN, what="This widget or canvas", tap=launches.tap
        ),
    ]


class GoneApp:
    """An old app canvas (.stapp.json) opened in the Workbench: app notebooks were replaced by widgets."""

    def open(self, text: str, full: str) -> dict[str, Any]:
        from swissarmybench_streamlit.domain.canvas_model import OLD_SAID

        raise ValueError(OLD_SAID)

    def write(self, body: dict[str, Any], path: str) -> str:
        from swissarmybench_streamlit.domain.canvas_model import OLD_SAID

        raise ValueError(OLD_SAID)


async def stop(services: Any) -> None:
    """When the server stops: no Streamlit process outlives it, nor its temporary folder."""
    previewer = getattr(services, "previewer", None)
    if previewer is not None:
        await previewer.stop()
    launches = getattr(services, "launches", None)
    if launches is not None:
        await launches.stop_all()
    live_runs = getattr(services, "live_runs", None)
    if live_runs is not None:
        await live_runs.stop_all()
    shared = getattr(services, "share_target", None)
    if shared is not None:
        await shared.close_all()


def canvas_pages(path: str, text: str) -> list[tuple[str, list[tuple[str, int]]]]:
    """A canvas's pages for the project's outline (its widgets are no notebook's cells: none linked)."""
    from swissarmybench_streamlit.domain import canvas_model

    if not path.endswith(canvas_model.SUFFIX):
        return []
    try:
        canvas = canvas_model.read(text).canvas
    except canvas_model.CanvasError as error:
        raise ValueError(str(error)) from None
    return [(str(page["name"]), []) for page in canvas.get("pages", [])]


def project_app(name: str) -> dict[str, Any]:
    """A new project's app (the base's BI project, as before this was an extension): an empty canvas named
    after the project, and Streamlit in its requirements."""
    from swissarmybench_streamlit.domain import canvas_build, canvas_model

    canvas = f"{canvas_build.slug(name)}{canvas_model.SUFFIX}"
    return {
        "files": {canvas: canvas_model.write(canvas_model.new_canvas(name))},
        "requirements": ["streamlit>=1.43"],
    }


def scaffold(name: str, data_names: list[str]) -> dict[str, Any]:
    """A Streamlit project's own files (beside data.ipynb and data.py): an empty canvas, nothing else (the
    owner, 2026-11-21: app notebooks were replaced by widgets)."""
    made = project_app(name)
    return {"app": False, "files": dict(made["files"]), "requirements": list(made["requirements"])}


def commands() -> dict[str, Any]:
    """Its agent commands, for the base's registry (cli/commands.py adds them when this is on)."""
    from swissarmybench_streamlit.commands import COMMANDS

    return COMMANDS


def __getattr__(name: str) -> Any:
    """The old names and arguments of its commands (cli/commands.py reads them as the base's)."""
    if name in ("OLD_NAMES", "OLD_ARGS"):
        from swissarmybench_streamlit import commands

        return getattr(commands, name)
    raise AttributeError(name)


def gone_commands() -> dict[str, str]:
    """Its commands that went (the old app canvas's), each with why: an old call says so."""
    from swissarmybench_streamlit.commands import GONE

    return GONE
