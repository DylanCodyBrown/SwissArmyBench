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
from swissarmybench.adapters.apis import ApiFiles, SpecSource
from swissarmybench.adapters.beta_log import BetaFiles, BetaSwitch
from swissarmybench.adapters.beta_log import listen as listen_for_crashes
from swissarmybench.adapters.blades import BladeStore
from swissarmybench.adapters.catalogs import CatalogStore
from swissarmybench.adapters.codegen import Verifier
from swissarmybench.adapters.database import PriorityWorkers, duckdb_grammar, open_database
from swissarmybench.adapters.datasets import DatasetStore
from swissarmybench.adapters.folders import ensure_own as ensure_own_folder
from swissarmybench.adapters.folders import listing as folder_listing
from swissarmybench.adapters.live_updates import LiveUpdates
from swissarmybench.adapters.packs import PackFolders
from swissarmybench.adapters.projects import ProjectFiles
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
from swissarmybench.adapters.updates import HttpFeed, UpdateSwitchFile, take_failure_note
from swissarmybench.adapters.views import ViewEngine
from swissarmybench.adapters.workbench import Documents
from swissarmybench.domain import python_connections
from swissarmybench.domain.blades import Blade
from swissarmybench.domain.grids import GridRegistry
from swissarmybench.renamed import env
from swissarmybench.server import blade_runner
from swissarmybench.server.blade_templates import TEMPLATES
from swissarmybench.server.kernels import Launcher
from swissarmybench.server.script_check import lint as script_lint
from swissarmybench.server.script_runner import ScriptRunner
from swissarmybench.server.streamlit_apps import Runner as StreamlitRunner
from swissarmybench.server.updater import Helper as UpdateHelper
from swissarmybench.services.agent import AgentService, Approvals, ExportTickets
from swissarmybench.services.analysis import Analysis
from swissarmybench.services.apis import Apis
from swissarmybench.services.beta_log import BetaLog
from swissarmybench.services.blades import BladeService
from swissarmybench.services.catalog_loading import CatalogLoading
from swissarmybench.services.catalogs import CatalogService
from swissarmybench.services.charts import Cards
from swissarmybench.services.codegen import CodeService
from swissarmybench.services.connections import ConnectionService
from swissarmybench.services.controllers import Controllers
from swissarmybench.services.datasets import ConnectionTables, DatasetService
from swissarmybench.services.export import Exports
from swissarmybench.services.folders import Folders
from swissarmybench.services.grids import GridService
from swissarmybench.services.inbox import Inbox
from swissarmybench.services.kind_colours import KindColours
from swissarmybench.services.lineage import Lineage
from swissarmybench.services.packs import Packs
from swissarmybench.services.panels import Panels
from swissarmybench.services.processes import ProcessRegistry, Sessions
from swissarmybench.services.profile import Profiles
from swissarmybench.services.projects import Projects
from swissarmybench.services.regression import Regression
from swissarmybench.services.relationships import Compares, Finder, KeyFinder, Models
from swissarmybench.services.script_export import ScriptExports
from swissarmybench.services.script_runs import ScriptRuns
from swissarmybench.services.snapshots import Snapshots
from swissarmybench.services.sql import SqlBox
from swissarmybench.services.streamlit import StreamlitApps
from swissarmybench.services.table_cells import TableCells
from swissarmybench.services.tieout import TieOut
from swissarmybench.services.timeseries import TimeSeries
from swissarmybench.services.updates import Updates
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
    apis: Apis
    catalog_loading: CatalogLoading
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
    table_cells: TableCells
    streamlit: StreamlitApps
    controllers: Controllers
    lineage: Lineage
    projects: Projects
    script_exports: ScriptExports
    panels: Panels
    kind_colours: KindColours
    script_runs: ScriptRuns
    beta: BetaLog
    updates: Updates
    live: LiveUpdates
    workers: PriorityWorkers


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
        return await blade_runner.run(
            job, settings.blade_timeout_seconds, report=lambda *e: process_event(kind, *e)
        )

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
    ws = Workspace(
        settings=settings,
        addresses=Addresses(port, token),
        store=store,
        # Derived view tables may use a quarter of the data budget; they are evicted freely.
        views=ViewEngine(connection, settings.max_total_bytes // 4),
        grids=GridRegistry(settings.max_grids),
        live=live,
        workers=workers,
        audit=AuditLog(state_dir / "audit.log" if audit_log else None),
        grammar=duckdb_grammar(),
        interrupted=duckdb.InterruptException,
        engine_error=duckdb.Error,
    )

    # ===== the beta log: errors, slow requests, processes, page errors and notes, redacted =====
    # (written only where the audit log is; beta mode on or off is beta.json, SWISSARMYBENCH_BETA wins)
    secret_values = (token, *(v for v in os.environ.values() if len(v) >= 8))
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
        secrets=lambda: secret_values,
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
    connections = ConnectionService(
        blades,
        TEMPLATES,
        on_saved=catalog_loading.saved,
        catalog_state=catalog_loading.state,
        tables=ConnectionTables(datasets),
        models=models,
        catalogs=catalogs,
    )
    # Add API: API_<name>.py beside data.py, or in the Workbench's own folder, and its connection.
    apis = Apis(ws, ApiFiles(), SpecSource(), connections, documents.made_default_folder)
    workbench_window = WorkbenchWindow(ws)

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
        failed=take_failure_note(failure_note),
    )
    return Services(
        settings=settings,
        ws=ws,
        datasets=datasets,
        grids=GridService(ws),
        profiles=Profiles(ws),
        analysis=Analysis(ws, verifier),
        regression=Regression(ws),
        timeseries=TimeSeries(ws),
        sql=SqlBox(ws, datasets, table_reader),
        exports=Exports(ws, export_writer, tickets, now=lambda: datetime.now(UTC)),
        codes=CodeService(ws, verifier),
        cards=Cards(ws, DashboardFiles(state_dir / "dashboards"), ThemeFiles(state_dir / "themes")),
        inbox=Inbox(ws),
        agent=AgentService(ws, approvals, tickets),
        sessions=Sessions(processes, store, live),
        catalogs=catalogs,
        blades=blades,
        connections=connections,
        apis=apis,
        catalog_loading=catalog_loading,
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
        table_cells=table_cells,
        panels=Panels(ws),
        script_runs=script_runs,
        kind_colours=KindColours(ws, JsonFile(state_dir / "kind_colours.json" if audit_log else None)),
        beta=beta,
        updates=updates,
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
        projects=Projects(
            ws,
            project_files,
            table_cells.group_cells,
            export_data=streamlit.export_data,
            remember=lambda path: documents.remember(path, time.time()),
            approvals=approvals,
        ),
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
