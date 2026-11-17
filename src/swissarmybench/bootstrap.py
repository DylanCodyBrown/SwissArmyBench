"""The composition root: the one place that builds the concrete adapters and hands them to the
service layer (the book's bootstrap script).

`bootstrap()` opens the locked database, starts the worker pool, and builds the stores (datasets,
views, catalogs, blades), the state files (audit log, the model library), the live updates
and the notebook. Each service gets these as its ports; no service or domain file imports an adapter.
The doors (server/app.py and its route modules) are given the services and nothing else.
"""

from __future__ import annotations

import asyncio
import os
import platform
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from swissarmybench import __version__
from swissarmybench.adapters import blade_run
from swissarmybench.adapters import datasets as table_reader
from swissarmybench.adapters import export as export_writer
from swissarmybench.adapters.apis import ApiFiles, ApiLibrary, SpecSource
from swissarmybench.adapters.beta_log import BetaFiles, BetaSwitch
from swissarmybench.adapters.beta_log import listen as listen_for_crashes
from swissarmybench.adapters.blades import BladeStore
from swissarmybench.adapters.catalogs import CatalogStore
from swissarmybench.adapters.claude import ClaudeFiles
from swissarmybench.adapters.codegen import Verifier
from swissarmybench.adapters.connection_colours import ColoursFile
from swissarmybench.adapters.database import PriorityWorkers, duckdb_grammar, open_database
from swissarmybench.adapters.datasets import DatasetStore
from swissarmybench.adapters.folders import ensure_own as ensure_own_folder
from swissarmybench.adapters.folders import listing as folder_listing
from swissarmybench.adapters.intellisense import JediWorld, Linters, ProjectModules
from swissarmybench.adapters.live_updates import LiveUpdates
from swissarmybench.adapters.packs import PackFolders
from swissarmybench.adapters.projects import ProjectFiles
from swissarmybench.adapters.sab_files import RecentProjects, SabArchive
from swissarmybench.adapters.state_files import (
    AuditLog,
    DashboardFiles,
    JsonFile,
    ModelFiles,
    ThemeFiles,
    info_file_path,
    is_own_file,
)
from swissarmybench.adapters.streamlit_files import AppFiles
from swissarmybench.adapters.structure_files import Codecs as StructureCodecs
from swissarmybench.adapters.structure_files import StructureFiles, rows_to_table
from swissarmybench.adapters.updates import HttpFeed, UpdateSwitchFile, take_failure_note, take_server_events
from swissarmybench.adapters.variables import ProcessEnvironment, VariableFiles, VariableKeyring
from swissarmybench.adapters.views import ViewEngine
from swissarmybench.adapters.workbench import Documents
from swissarmybench.client import kernel_intel
from swissarmybench.domain import context_md as context_rules
from swissarmybench.domain import projects as project_rules
from swissarmybench.domain import python_connections
from swissarmybench.domain.blades import Blade, env_settings
from swissarmybench.domain.context_md import CatalogTable
from swissarmybench.domain.grids import GridRegistry
from swissarmybench.domain.project_scope import APP_FOLDER
from swissarmybench.domain.steps import describe_steps
from swissarmybench.renamed import env
from swissarmybench.server import blade_runner
from swissarmybench.server.autostart import Autostart
from swissarmybench.server.blade_templates import TEMPLATES
from swissarmybench.server.claude_finder import Finder as ClaudeFinder
from swissarmybench.server.claude_finder import RecordingStarter, StandinFinder, own_command
from swissarmybench.server.claude_finder import Starter as ClaudeStarter
from swissarmybench.server.kernels import Launcher
from swissarmybench.server.script_check import lint as script_lint
from swissarmybench.server.script_runner import ScriptRunner
from swissarmybench.server.streamlit_apps import Runner as StreamlitRunner
from swissarmybench.server.updater import Helper as UpdateHelper
from swissarmybench.services.agent import AgentService, Approvals, ExportTickets
from swissarmybench.services.analysis import Analysis
from swissarmybench.services.api_explorer import Explorer as ApiExplorer
from swissarmybench.services.apis import Apis
from swissarmybench.services.beta_log import BetaLog
from swissarmybench.services.blades import BladeService
from swissarmybench.services.catalog_loading import CatalogLoading
from swissarmybench.services.catalogs import CatalogService
from swissarmybench.services.charts import Cards
from swissarmybench.services.claude import Claude
from swissarmybench.services.codegen import CodeService
from swissarmybench.services.connection_colours import ConnectionColours
from swissarmybench.services.connection_swap import ConnectionSwap
from swissarmybench.services.connection_tables import ConnectionTables as ConnectionTablesService
from swissarmybench.services.connection_usage import ConnectionUsage
from swissarmybench.services.connections import ConnectionService
from swissarmybench.services.context_md import ContextMd
from swissarmybench.services.controllers import Controllers
from swissarmybench.services.datasets import ConnectionTables, DatasetService
from swissarmybench.services.export import Exports
from swissarmybench.services.folders import Folders
from swissarmybench.services.grids import GridService
from swissarmybench.services.inbox import Inbox
from swissarmybench.services.intellisense import Intellisense
from swissarmybench.services.kind_colours import KindColours
from swissarmybench.services.lineage import Lineage
from swissarmybench.services.navigation import Navigation
from swissarmybench.services.packs import Packs
from swissarmybench.services.panels import Panels
from swissarmybench.services.processes import ProcessRegistry, Sessions
from swissarmybench.services.profile import Profiles
from swissarmybench.services.project_scope import ProjectScope
from swissarmybench.services.projects import Projects
from swissarmybench.services.regression import Regression
from swissarmybench.services.relationships import Compares, Finder, KeyFinder, Models
from swissarmybench.services.sab_projects import SabProjects
from swissarmybench.services.script_export import ScriptExports
from swissarmybench.services.script_runs import ScriptRuns
from swissarmybench.services.session_log import Heard, SessionLog
from swissarmybench.services.snapshots import Snapshots
from swissarmybench.services.sql import SqlBox
from swissarmybench.services.streamlit import StreamlitApps
from swissarmybench.services.structures import Structures
from swissarmybench.services.table_cells import TableCells
from swissarmybench.services.tieout import TieOut
from swissarmybench.services.timeseries import TimeSeries
from swissarmybench.services.updates import Updates
from swissarmybench.services.variables import Variables
from swissarmybench.services.workbench import Workbench
from swissarmybench.services.workbench_window import WorkbenchWindow
from swissarmybench.services.workspace import Addresses, Workspace
from swissarmybench.settings import Settings


@dataclass
class Services:
    """What the doors are given: the use cases, one service per feature, and the three adapters the
    entry point drives itself (the sockets of the live updates, the worker pool it closes and the
    sessions' registry it prunes)."""

    settings: Settings
    ws: Workspace
    datasets: DatasetService
    grids: GridService
    profiles: Profiles
    analysis: Analysis
    regression: Regression
    timeseries: TimeSeries
    sql: SqlBox
    exports: Exports
    codes: CodeService
    cards: Cards
    agent: AgentService
    inbox: Inbox
    sessions: Sessions
    catalogs: CatalogService
    blades: BladeService
    connections: ConnectionService
    connection_usage: ConnectionUsage
    apis: Apis
    structures: Structures
    api_explorer: ApiExplorer
    catalog_loading: CatalogLoading
    connection_tables: ConnectionTablesService
    folders: Folders
    workbench: Workbench
    models: Models
    finder: Finder
    packs: Packs
    keys: KeyFinder
    compares: Compares
    tie_out: TieOut
    snapshots: Snapshots
    workbench_window: WorkbenchWindow
    intellisense: Intellisense
    table_cells: TableCells
    streamlit: StreamlitApps
    controllers: Controllers
    lineage: Lineage
    projects: Projects
    sab_projects: SabProjects
    project_scope: ProjectScope
    script_exports: ScriptExports
    panels: Panels
    session_log: SessionLog
    variables: Variables
    connection_swap: ConnectionSwap
    navigation: Navigation
    kind_colours: KindColours
    connection_colours: ConnectionColours
    script_runs: ScriptRuns
    beta: BetaLog
    updates: Updates
    claude: Claude
    context_md: ContextMd
    live: LiveUpdates
    workers: PriorityWorkers


def usage_documents(
    documents: Documents, streamlit: StreamlitApps, sab_projects: SabProjects, project_files: ProjectFiles
) -> list[str]:
    """Where the Connections page looks for a connection's references: with a project open, its own
    notebooks, scripts and apps (everything is the project's, 2026-11-16) and the documents open in a
    Workbench window; with none, the Workbench's recent files and the open documents. Each file once,
    by its real path (one notebook reached by two spellings was listed twice)."""
    paths = list(streamlit.documents())
    folder = (sab_projects.state().get("project") or {}).get("folder")
    if folder:
        try:
            names = project_files.names(folder)
        except OSError:
            names = []
        paths += [project_files.path(folder, n) for n in project_rules.project_files(names)]
    else:
        paths += [str(r["path"]) for r in documents.recent() if r.get("exists")]
    seen: dict[str, str] = {}
    for path in paths:
        seen.setdefault(os.path.realpath(path), path)
    return list(seen.values())


def bootstrap(
    port: int,
    token: str,
    settings: Settings | None = None,
    on_shutdown: Callable[[], None] | None = None,
    audit_log: bool = True,
) -> Services:
    """Build everything for a server listening on 127.0.0.1:`port` that accepts `token`."""
    settings = settings or Settings()
    state_dir, export_dir = settings.state_dir, settings.export_dir

    # ===== the adapters =====
    connection = open_database(settings.duckdb_memory_limit)
    workers = PriorityWorkers(settings.worker_threads)
    store = DatasetStore(
        connection, settings.max_dataset_bytes, settings.max_total_bytes, settings.max_datasets
    )
    live = LiveUpdates()
    # Packs: installed Claude Code plugins that carry blades and tangs, and editable clones in the
    # blade folders. Their blades and tangs join the blade store and the tang library read-only.
    pack_files = PackFolders(
        settings.claude_dir,
        shared=lambda: [f["path"] for f in blade_store.folders() if f["exists"]],
        environ=os.environ,
    )
    blade_store = BladeStore(
        settings.blades_dir,
        library=state_dir / "library",
        folders_file=state_dir / "blade_folders.json",
        pins_file=state_dir / "blade_pins.json",
        packs=pack_files.blade_dirs,
        # The built-in starter pack ships inside the package, so each version brings its own.
        starters=Path(__file__).resolve().parent / "starters",
    )
    verifier = Verifier(settings.duckdb_memory_limit)

    def process_event(
        kind: str, event: str, code: int | None, seconds: float | None, reason: str = ""
    ) -> None:
        beta.process(kind, event, code, seconds, reason)

    async def run_blade(
        blade: Blade, mode: str, typed: dict[str, str], extra: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        job = blade_runner.payload(blade_store, blade, mode, typed, extra)
        kind = "catalog" if mode == "catalog" else "blade"
        # A connection's run through the app (a catalog load, a table read, a query, a test) is a call
        # the Connections page counts (services/connection_usage.py; memory only).
        try:
            answer = await blade_runner.run(
                job, settings.blade_timeout_seconds, report=lambda *e: process_event(kind, *e)
            )
        except Exception:
            connection_usage.record(blade.name, mode, ok=False)
            raise
        connection_usage.record(blade.name, mode, ok=True)
        return answer

    async def vault_values(wanted: dict[str, dict[str, str]]) -> tuple[dict[str, str], list[str]]:
        """A scheduled script's variables from key vaults (vault -> variable -> secret), and what failed."""
        sources = {
            variable: {"from": "vault", "vault": vault, "secret": secret}
            for vault, mapping in wanted.items()
            for variable, secret in mapping.items()
        }
        try:
            jobs = python_connections.vault_jobs(sources, blade_store.get, blade_store.saved_secrets)
            answer = await blade_runner.run(
                {"mode": "load", "label": "the vaults", "kind": "load", "vaults": jobs},
                settings.vault_timeout_seconds,
            )
        except (python_connections.PythonConnectionError, blade_runner.RefreshError) as error:
            return {}, [str(error)]
        values = {str(k): str(v) for k, v in dict(answer.get("values") or {}).items()}
        return values, [str(p) for p in answer.get("problems") or []]

    def secrets_of(name: str) -> list[str] | None:
        """A connection's or blade's passwords by the names its code asks secret() for (None: none here)."""
        try:
            return blade_store.get(name).secrets
        except KeyError:
            return None

    def files_of(name: str) -> list[str]:
        """A connection's certificate and keystore files read from a variable: those variables."""
        try:
            return [m["variable"] for m in env_settings(blade_store.get(name).code)]
        except KeyError:
            return []

    async def vault_environment() -> tuple[dict[str, str], list[str]]:
        """Every vault's entries for a Workbench kernel about to start, and the vaults that failed."""
        job = blade_runner.load_payload(blade_store)
        if job is None:
            return {}, []
        try:
            answer = await blade_runner.run(job, settings.vault_timeout_seconds)
        except blade_runner.RefreshError as error:
            why = str(error)
            if "did not finish" in why:
                seconds = settings.vault_timeout_seconds
                why = f"Reading the vaults took over {seconds:.0f} seconds: this kernel started without them."
            return {}, [why]
        values = {str(k): str(v) for k, v in dict(answer.get("values") or {}).items()}
        return values, [str(p) for p in answer.get("problems") or []]

    # ===== the workspace: the ports every use case shares =====
    session_log = SessionLog(live, JsonFile(state_dir / "follow.json" if audit_log else None))
    ws = Workspace(
        settings=settings,
        addresses=Addresses(port, token),
        store=store,
        # Derived view tables may use a quarter of the data budget; they are evicted freely.
        views=ViewEngine(connection, settings.max_total_bytes // 4),
        grids=GridRegistry(settings.max_grids),
        live=live,
        workers=workers,
        # The audit log, heard by the Session page's log (this session's entries, each naming its object).
        audit=Heard(AuditLog(state_dir / "audit.log" if audit_log else None), session_log),
        grammar=duckdb_grammar(),
        interrupted=duckdb.InterruptException,
        engine_error=duckdb.Error,
    )

    # ===== the beta log: errors, slow requests, processes, page errors and notes, redacted =====
    # (written only where the audit log is; beta mode on or off is beta.json, SWISSARMYBENCH_BETA wins)
    # Read each time: the Variables page's values join the environment as they are added.
    beta = BetaLog(
        ws,
        BetaFiles(state_dir / "logs" if audit_log else None, settings.beta_log_bytes, settings.beta_log_days),
        BetaSwitch(state_dir / "beta.json" if audit_log else None),
        variable=env("SWISSARMYBENCH_BETA"),
        facts={
            "version": __version__,
            "os": f"{platform.system()} {platform.release()}",
            "python": platform.python_version(),
        },
        home=str(Path.home()),
        names=lambda: {
            "table": [info.name for info in store.all()],
            "column": [c.name for info in store.all() for c in info.columns],
        },
        # Never in a message: the server's token, and any environment variable's value.
        secrets=lambda: (token, *(v for v in os.environ.values() if len(v) >= 8)),
        listen=listen_for_crashes,
        now=time.time,
    )

    # ===== the services =====
    processes = ProcessRegistry()  # the Python sessions offering tables to the Open list
    tickets = ExportTickets()  # the agent exports the user approved, not yet written
    # The questions for the user that the agent's requests wait on (the page's approval prompt): one
    # for every use case that writes the user's rows to disk for the agent.
    approvals = Approvals(live)
    datasets = DatasetService(
        ws,
        table_reader,
        processes,
        own_file=lambda path: is_own_file(path, state_dir, export_dir),
        on_shutdown=on_shutdown or (lambda: None),
    )
    catalogs = CatalogService(
        ws, CatalogStore(connection, settings.max_catalogs, settings.max_catalog_rows), table_reader
    )
    blades = BladeService(
        ws,
        blade_store,
        catalogs,
        TEMPLATES,
        blade_run.needed,
        run_blade,
        blade_runner.install_packages,
        python=sys.executable,
        environ=os.environ,
    )
    catalog_loading = CatalogLoading(
        ws, blades, catalogs, settings.auto_load_catalogs, settings.catalogs_at_once
    )
    # Tangs come from the person's own folder and the shared folders, which are the blade folders:
    # one team folder carries blades and tangs alike.
    compares = Compares(ws)
    models = Models(
        ws,
        ModelFiles(
            state_dir,
            shared=lambda: [f["path"] for f in blade_store.folders() if f["exists"]],
            packs=pack_files.tang_dirs,
        ),
    )
    datasets.renamed.append(models.rename_table)
    documents = Documents(state_dir / "recent.json", settings.workbench_dir)
    script_runs = ScriptRuns(
        ws,
        JsonFile(state_dir / "run_settings.json" if audit_log else None),
        documents,
        ScriptRunner(),
        os.environ,
        default_python=lambda: sys.executable,
        secrets_of=secrets_of,
        vault_values=vault_values,
        now=time.time,
        files_of=files_of,
    )
    table_cells = TableCells(ws, datasets.origins)
    project_files = ProjectFiles()
    # Streamlit: a canvas's pages and a document's live cells, written to a temporary folder of the
    # app's own and run in the document's own Python (Streamlit is never this app's dependency).
    app_files = AppFiles()
    streamlit_runner = StreamlitRunner(report=lambda *e: process_event("streamlit", *e))
    streamlit = StreamlitApps(
        ws,
        app_files,
        streamlit_runner,
        export_writer,
        now=time.time,
        read_document=documents.read,
        environment_of=documents.environment,
        project_files=project_files,
        table_cells=table_cells.group_cells,
        arrange=table_cells.arrange,
        approvals=approvals,
    )
    workbench = Workbench(
        ws,
        documents,
        Launcher(report=lambda *e: process_event("kernel", *e)),
        os.environ,
        now=time.time,
        folder_of=lambda path: str(Path(path).expanduser().parent),
        secret_names=blades.environment_names,
        vault_environment=vault_environment,
        kernel_stopped=streamlit.kernel_stopped,
    )
    kind_colours = KindColours(ws, JsonFile(state_dir / "kind_colours.json" if audit_log else None))
    # Each connection's colour: this computer's colours.toml (the library's later, by its path), the same
    # in every project; never one of the rail's (the kind colours, the accent).
    connection_colours = ConnectionColours(
        ws,
        blades,
        ColoursFile(state_dir / "colours.toml" if audit_log else None),
        kind_colours.chosen,
    )
    connections = ConnectionService(
        blades,
        TEMPLATES,
        on_saved=catalog_loading.saved,
        catalog_state=catalog_loading.state,
        tables=ConnectionTables(datasets),
        models=models,
        catalogs=catalogs,
        colours=connection_colours,
    )
    # The Connections page: each connection's references, configuration and calls this session.
    connection_usage = ConnectionUsage(
        ws,
        blades,
        connections,
        documents=lambda: usage_documents(documents, streamlit, sab_projects, project_files),
        read=documents.read,
        origin_of=datasets.origins.get,
        environ=os.environ,
        now=time.time,
    )
    # Add API: this computer's library (apis/<name>/): API_<name>.py, its API blade and web call blades.
    apis = Apis(
        ws,
        ApiFiles(),
        SpecSource(),
        connections,
        ApiLibrary(state_dir / "library" / "apis"),
        blades,
        now=lambda: datetime.now(UTC).isoformat(timespec="seconds"),
    )
    workbench_window = WorkbenchWindow(ws)
    dashboards = DashboardFiles(state_dir / "dashboards")
    cards = Cards(ws, dashboards, ThemeFiles(state_dir / "themes"))
    projects = Projects(
        ws,
        project_files,
        table_cells.group_cells,
        export_data=streamlit.export_data,
        remember=lambda path: documents.remember(path, time.time()),
        approvals=approvals,
    )
    # A project as one .sab file: unpacked into a working folder while open, written back on Save.
    archive = SabArchive(
        settings.max_project_file_bytes,
        settings.max_project_entries,
        settings.max_project_unpacked_bytes,
        settings.project_temp_dir,
    )
    # This computer's saved connections and blades (the ones saved before projects held their own): the
    # blades in use while no project is open, and a place to import from.
    computer_blades = BladeStore(settings.blades_dir)

    async def use_project(folder: str | None) -> None:
        """The stores follow the open project: its own connections, blades and saved dashboards (in its
        working folder's .sab folder), or this computer's with none open. Catalogs follow its connections."""
        app = Path(folder) / APP_FOLDER if folder else None
        blade_store.use(app / "blades" if app else settings.blades_dir, keep_secrets=app is not None)
        dashboards.folder = app / "dashboards" if app else state_dir / "dashboards"
        await catalog_loading.rescope()
        await variables.rescope()
        await live.broadcast({"type": "blades_changed"})
        if structures_ready:
            await structures_ready[0].project_changed(folder)  # the closed project's structures go with it

    structures_ready: list[Structures] = []  # set once built (below): use_project is made before it

    def carry_connections(folder: str, names: list[str]) -> None:
        """A new project's open tables' connections, copied in from this computer's (and the vaults
        their passwords come from)."""
        wanted: dict[str, Blade] = {}
        for name in names:
            try:
                blade = computer_blades.get(name)
            except KeyError:
                continue
            if blade.path or blade.pack:
                continue  # a blade folder's or a pack's: read-only libraries, there in every project
            wanted[blade.name.casefold()] = blade
            vaults, _ = computer_blades.providers(blade)
            wanted |= {v.name.casefold(): v for v in vaults if not v.path and not v.pack}
        files = dict(computer_blades.saved_files())
        for blade in wanted.values():
            file = BladeStore.file_name(blade.name)
            if file in files:
                archive.write_into(folder, f"{APP_FOLDER}/blades/{file}", files[file])

    sab_projects = SabProjects(
        ws,
        archive,
        RecentProjects(state_dir / "recent_projects.json" if audit_log else None),
        datasets,
        connections,
        cards,
        models,
        projects,
        table_reader,
        approvals,
        version=__version__,
        now=time.time,
        kernel_document=workbench.document_of,
        ask_workbench=lambda command, args: workbench_window.ask(command, args, "app"),
        scope=use_project,
        carry=carry_connections,
        autosave_seconds=settings.autosave_seconds,
    )
    # Structures: nested data (JSON, YAML, XML, TOML) as documents; the project's own in structures/.
    structures = Structures(
        ws,
        StructureFiles(),
        StructureCodecs(),
        datasets,
        rows_to_table,
        project_folder=lambda: sab_projects.current.folder if sab_projects.current else None,
        default_folder=documents.made_default_folder,
        documents=lambda: usage_documents(documents, streamlit, sab_projects, project_files),
        read_document=documents.read,
    )
    structures_ready.append(structures)
    # The APIs page: the library's APIs explored; a call sent opens in Structures, its origin the call.
    api_explorer = ApiExplorer(
        ws,
        apis,
        ApiLibrary(state_dir / "library" / "apis"),
        SpecSource(),
        blades,
        connections,
        connection_usage,
        structures,
        approvals,
        now=lambda: datetime.now(UTC).isoformat(timespec="seconds"),
        to_thread=asyncio.to_thread,
        reader=table_reader,
    )
    structures.rerun = api_explorer.run_again
    blades.web_call_saved.append(api_explorer.tables_changed)
    structures.grid_steps = lambda table: (
        describe_steps(grid.steps) if (grid := ws.grids.first_for(table)) is not None else []
    )
    sab_projects.manifest_extras.append(lambda: {"structures": {"open": structures.open_paths()}})
    sab_projects.opened.append(structures.project_changed)
    # A table's connection swapped for another (its steps kept), and the code that named the old one.
    # What a connection is: its tables, listed and read one way for every kind; DuckDB SQL names them.
    connection_tables = ConnectionTablesService(
        ws, connections, catalogs, catalog_loading, table_reader.table_to_arrow_stream
    )
    datasets.connection_sql = connection_tables
    connection_swap = ConnectionSwap(
        ws,
        datasets,
        connections,
        catalogs,
        catalog_loading,
        sab_projects,
        connection_usage,
        table_reader,
        read_document=documents.read,
        write_document=lambda path, text: documents.write(path, text, True),
        open_documents=streamlit.documents,
        ask_window=lambda command, args: workbench_window.ask(command, args, "app"),
    )
    project_scope = ProjectScope(
        sab_projects, archive, computer_blades, connections, on_saved=catalog_loading.saved
    )
    # The Variables page: this computer's variables (never a project's): the shareable file and the local
    # values; their values given to this server's environment, so what it runs and starts reads them.
    variables_file = VariableFiles(
        state_dir / "variables.json" if audit_log else None,
        state_dir / "local" / "variables.json" if audit_log else None,
    )

    async def save_variable_blade(data: dict[str, Any], previous: str, who: str) -> Any:
        saved = await blades.save(data, previous, who)
        catalog_loading.saved(str(saved["name"]))
        return saved

    variables = Variables(
        ws,
        variables_file,
        VariableKeyring(),
        ProcessEnvironment(),
        blade_store,
        save_variable_blade,
        documents=lambda: usage_documents(documents, streamlit, sab_projects, project_files),
        read=documents.read,
        run_settings=script_runs,
        kernels=workbench.kernel_count,
    )

    async def open_work() -> dict[str, Any]:
        """What is open (the tray's menu) and what an update would lose: the tables, the Workbench
        window's documents (when one is open), the documents with unsaved changes, the kernels."""
        tables = [{"grid": g.id, "name": g.dataset} for g in ws.grids.all() if store.get(g.dataset)]
        documents: list[dict[str, Any]] = []
        if live.workbench_open():
            try:
                answer = await asyncio.wait_for(workbench_window.ask("documents", {}, "app"), 3.0)
                listed = answer.get("documents", []) if isinstance(answer, dict) else []
                documents = [
                    {
                        "key": d.get("index"),
                        "title": d.get("title"),
                        "unsaved": d.get("unsaved_changes") is True,
                    }
                    for d in listed
                    if isinstance(d, dict) and d.get("kind") in ("notebook", "script", "app")
                ]
            except Exception:  # noqa: S110 (a window that does not answer lists nothing)
                pass
        titles = [str(d["title"]) for d in documents if d["unsaved"]] + streamlit.unsaved()
        return {
            "tables": tables,
            "documents": documents,
            "unsaved": list(dict.fromkeys(titles)),
            "kernels": workbench.kernel_count(),
        }

    # Start at sign-in: the user's own entry, or one under a test's home folder.
    home = settings.autostart_home
    autostart = (
        Autostart(home=home, environ={"APPDATA": str(home / "AppData" / "Roaming")}) if home else Autostart()
    )
    # The update check (the one request that leaves the computer, the owner's call) and Update to X.
    failure_note = state_dir / "update_failed.json" if audit_log else None
    updates = Updates(
        current=__version__,
        feeds=settings.update_feeds,
        feed=HttpFeed(),
        switch=UpdateSwitchFile(state_dir / "update.json" if audit_log else None),
        helper=UpdateHelper(info_file_path(), state_dir / "update_failed.json"),
        open_work=open_work,
        approvals=approvals,
        audit=ws.audit,
        live=live,
        stop=on_shutdown or (lambda: None),
        autostart=autostart,
        failed=take_failure_note(failure_note),
    )
    # Launch Claude: Claude Code in the user's terminal, or Claude Desktop, found wherever it is installed.
    standin = settings.claude_standin
    claude_files = ClaudeFiles(state_dir / "claude", state_dir / "claude.json" if audit_log else None)
    agent = AgentService(ws, approvals, tickets)

    async def catalog_of(name: str) -> Any:
        """A loaded catalog's schemas (datasets), its first tables, their count, and the names shared."""
        schemas = await catalogs.schema_names(name)
        if schemas is None:
            return None
        tables: list[CatalogTable] = []
        for s in schemas:
            if len(tables) >= context_rules.MAX_CATALOG_TABLES:
                break
            if not s.get("tables") and not s.get("views"):
                continue
            found = await catalogs.tables(
                name, str(s["schema"]), str(s["database"]) or None, 0, context_rules.MAX_CATALOG_TABLES
            )
            tables += [
                CatalogTable(str(t["database"]), str(t["schema"]), str(t["table"])) for t in found["tables"]
            ]
        total = sum(int(s.get("tables") or 0) + int(s.get("views") or 0) for s in schemas)
        return (
            [str(s["schema"]) for s in schemas],
            tables[: context_rules.MAX_CATALOG_TABLES],
            total,
            await catalogs.shared_tables(name),
        )

    def used_in(name: str) -> list[tuple[str, str]]:
        """The project's documents and the open grids that use a connection (kind, path or table)."""
        folder = (sab_projects.state().get("project") or {}).get("folder")
        found, _ = connection_usage.references(name)
        out = []
        for ref in found:
            if ref.kind == "grid":
                out.append(("grid", ref.title))
            elif folder and ref.document.replace("\\", "/").casefold().startswith(
                str(folder).replace("\\", "/").rstrip("/").casefold() + "/"
            ):
                out.append((ref.kind, ref.document))
        return out

    intellisense = Intellisense(
        ws,
        kernel_intel.answer,
        JediWorld(),
        ProjectModules(),
        Linters(),
        kernel_of=workbench.kernel_or_none,
        project_folder=lambda: (sab_projects.state().get("project") or {}).get("folder"),
        blades=lambda: blades.listing()["blades"],
        variables=lambda: variables.listing()["variables"],
        structures=lambda: sorted({str(f.get("name")) for f in structures.files()}),
        dialect_of=lambda name: next(
            (b.dialect for b in blade_store.all() if b.name.casefold() == name.casefold()), None
        ),
        read_file=lambda path: documents.read(path)[0],
    )
    context_md = ContextMd(
        ws,
        claude_files,
        version=__version__,
        project=lambda: sab_projects.state().get("project"),
        connections=lambda: connection_usage.overview()["connections"],
        colour_of=connection_colours.colour_of,
        catalog=catalog_of,
        used_in=used_in,
        origin_of=datasets.origins.get,
        relationships=models.current,
        variables=lambda: variables.listing(),
        documents=lambda: project_scope.documents(),
        windows=lambda: {
            "home": live.workspace_open(),
            "front": agent.active_grid,
            "workbench": live.workbench_open(),
            "kernels": workbench.running_documents(),
            "blades": live.catalog_open(),
        },
        changes=lambda: live.changes,
        apis=api_explorer.listing,
        structures=structures.listing,
    )
    claude = Claude(
        ws,
        StandinFinder(standin) if standin else ClaudeFinder(),
        RecordingStarter(standin.with_suffix(".launches.jsonl")) if standin else ClaudeStarter(),
        claude_files,
        version=__version__,
        home=str(Path.home()),
        environ=dict(os.environ),
        commands=own_command,
        project=lambda: sab_projects.state().get("project"),
        connections=lambda: connections.listing()["connections"],
        documents=lambda: project_scope.documents()["documents"],
        context_md=context_md,
    )
    # What the tray saw while no server ran (a crash, its restarts, giving up): into the beta log now.
    for event in take_server_events(state_dir / "server_events.json" if audit_log else None):
        beta.process("server", str(event["event"]), event.get("code"), None, str(event.get("reason") or ""))
    return Services(
        settings=settings,
        ws=ws,
        datasets=datasets,
        grids=GridService(ws, datasets.origins.get),
        profiles=Profiles(ws),
        analysis=Analysis(ws, verifier),
        regression=Regression(ws),
        timeseries=TimeSeries(ws),
        sql=SqlBox(ws, datasets, table_reader),
        exports=Exports(ws, export_writer, tickets, now=lambda: datetime.now(UTC)),
        codes=CodeService(ws, verifier),
        cards=cards,
        inbox=Inbox(ws),
        agent=agent,
        sessions=Sessions(processes, store, live),
        catalogs=catalogs,
        blades=blades,
        connections=connections,
        connection_usage=connection_usage,
        apis=apis,
        structures=structures,
        api_explorer=api_explorer,
        catalog_loading=catalog_loading,
        connection_tables=connection_tables,
        folders=Folders(folder_listing, lambda where: ensure_own_folder(where, settings.workbench_dir)),
        workbench=workbench,
        models=models,
        finder=Finder(ws, models),
        packs=Packs(ws, pack_files, blade_store, models.library_files),
        keys=KeyFinder(ws),
        compares=compares,
        tie_out=TieOut(compares),
        snapshots=Snapshots(ws),
        workbench_window=workbench_window,
        intellisense=intellisense,
        table_cells=table_cells,
        panels=Panels(ws),
        session_log=session_log,
        variables=variables,
        connection_swap=connection_swap,
        navigation=Navigation(ws),
        script_runs=script_runs,
        kind_colours=kind_colours,
        connection_colours=connection_colours,
        beta=beta,
        updates=updates,
        claude=claude,
        context_md=context_md,
        streamlit=streamlit,
        # A canvas page's controllers: its check, Test this page (AppTest in the app's Python), thin cells.
        controllers=Controllers(streamlit, app_files, streamlit_runner, project_files),
        # A cell's lineage back to the data, each step's value from its kernel, a live page or the grid.
        lineage=Lineage(
            ws,
            streamlit,
            datasets.origins,
            documents.read,
            project_files,
            workbench.lineage_values,
            app_files.read_trace,
        ),
        projects=projects,
        sab_projects=sab_projects,
        project_scope=project_scope,
        # Export as one Python script: the document's cells, its connections' own code, ruff's check.
        script_exports=ScriptExports(
            ws,
            blade_store,
            read_document=documents.read,
            write_document=documents.write,
            arrange=table_cells.arrange,
            lint=script_lint,
            folder_of=lambda path: str(Path(path).expanduser().parent),
            join=lambda folder, name: str(Path(folder) / name),
            inline=apis.inline,  # an API_<name>.py the document imports travels inside the export
        ),
        live=live,
        workers=workers,
    )
