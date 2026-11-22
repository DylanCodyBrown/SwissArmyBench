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
import sysconfig
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, cast

import duckdb

from swissarmybench import __version__
from swissarmybench import extensions as extension_modules
from swissarmybench.adapters import blade_run, sab_adapter
from swissarmybench.adapters import code_files as code_file_disk
from swissarmybench.adapters import datasets as table_reader
from swissarmybench.adapters import export as export_writer
from swissarmybench.adapters.apis import ApiFiles, ApiLibrary, SpecSource
from swissarmybench.adapters.app_registrations import MicrosoftProbe, RegistrationFiles
from swissarmybench.adapters.beta_log import BetaFiles, BetaSwitch
from swissarmybench.adapters.beta_log import listen as listen_for_crashes
from swissarmybench.adapters.blades import BladeStore
from swissarmybench.adapters.catalogs import CatalogStore
from swissarmybench.adapters.claude import ClaudeFiles
from swissarmybench.adapters.codegen import Verifier
from swissarmybench.adapters.connection_colours import ColoursFile
from swissarmybench.adapters.database import PriorityWorkers, duckdb_grammar, grammar_later, open_database
from swissarmybench.adapters.datasets import DatasetStore, file_stamp
from swissarmybench.adapters.extensions import discover as discover_extensions
from swissarmybench.adapters.folders import ensure_own as ensure_own_folder
from swissarmybench.adapters.folders import is_folder, make_folder
from swissarmybench.adapters.folders import listing as folder_listing
from swissarmybench.adapters.folders import places as folder_places
from swissarmybench.adapters.found_connections import ConnectionFinder
from swissarmybench.adapters.intellisense import JediWorld, Linters, ProjectModules
from swissarmybench.adapters.library import LibraryFolder
from swissarmybench.adapters.live_updates import LiveUpdates
from swissarmybench.adapters.project_explorer import ExplorerFiles, ExplorerSettings
from swissarmybench.adapters.projects import ProjectFiles
from swissarmybench.adapters.sab_files import RecentProjects, SabArchive
from swissarmybench.adapters.sandbox import ExportFolder, LocalApiFiles, SandboxFiles
from swissarmybench.adapters.script_ide import ScriptCode
from swissarmybench.adapters.shared_catalog import CatalogFiles
from swissarmybench.adapters.state_files import (
    AuditLog,
    DashboardFiles,
    JsonFile,
    ModelFiles,
    ThemeFiles,
    info_file_path,
    is_own_file,
)
from swissarmybench.adapters.structure_files import Codecs as StructureCodecs
from swissarmybench.adapters.structure_files import StructureFiles, rows_to_table
from swissarmybench.adapters.team import TeamFiles
from swissarmybench.adapters.tunnels import TunnelFiles
from swissarmybench.adapters.updates import HttpFeed, UpdateSwitchFile, take_failure_note
from swissarmybench.adapters.variables import (
    ProcessEnvironment,
    VariableFiles,
    VariableKeyring,
    backup_copies,
)
from swissarmybench.adapters.vault_names import VaultNameFiles
from swissarmybench.adapters.views import ViewEngine
from swissarmybench.adapters.workbench import Documents
from swissarmybench.client import kernel_intel
from swissarmybench.domain import api_targets as api_target_rules
from swissarmybench.domain import blade_tables, python_connections
from swissarmybench.domain import connection_slots as slot_rules
from swissarmybench.domain import connection_tables as connection_table_rules
from swissarmybench.domain import connection_usage as usage_rules
from swissarmybench.domain import connections as connection_rules
from swissarmybench.domain import context_md as context_rules
from swissarmybench.domain import extensions as extension_rules
from swissarmybench.domain import library as library_rules
from swissarmybench.domain import library_setup as setup_rules
from swissarmybench.domain import local_api as local_api_rules
from swissarmybench.domain import portability as portability_rules
from swissarmybench.domain import projects as project_rules
from swissarmybench.domain import sandbox as sandbox_rules
from swissarmybench.domain import variables as variable_rules
from swissarmybench.domain.blades import Blade, env_settings
from swissarmybench.domain.connection_swap import Place
from swissarmybench.domain.context_md import CatalogTable
from swissarmybench.domain.grids import GridRegistry
from swissarmybench.domain.project_explorer import local_only_words as explorer_rules_words
from swissarmybench.domain.project_scope import APP_FOLDER
from swissarmybench.domain.sab_files import APP_GITIGNORE, APP_IGNORE_FILE
from swissarmybench.domain.steps import describe_steps
from swissarmybench.domain.table_cells import Origin as TableOrigin
from swissarmybench.server import api_runs, api_runtime, blade_runner, dialog_runner, file_manager
from swissarmybench.server.blade_templates import TEMPLATES
from swissarmybench.server.claude_finder import Finder as ClaudeFinder
from swissarmybench.server.claude_finder import RecordingStarter, StandinFinder, own_command
from swissarmybench.server.claude_finder import Starter as ClaudeStarter
from swissarmybench.server.desktop import SystemShell, qt_version
from swissarmybench.server.kernels import Launcher
from swissarmybench.server.script_check import lint as script_lint
from swissarmybench.server.text_process import run_text
from swissarmybench.server.tunnels import DevTunnelProgram
from swissarmybench.server.updater import Helper as UpdateHelper
from swissarmybench.services import explorer as explorer_providers
from swissarmybench.services.agent import AgentService, Approvals, ExportTickets
from swissarmybench.services.analysis import Analysis
from swissarmybench.services.analyze import Analyze
from swissarmybench.services.api_explorer import Explorer as ApiExplorer
from swissarmybench.services.api_export import ApiExport
from swissarmybench.services.apis import Apis
from swissarmybench.services.app_registrations import AppRegistrations
from swissarmybench.services.beta_log import BetaLog
from swissarmybench.services.blades import BladeService
from swissarmybench.services.catalog_loading import CatalogLoading
from swissarmybench.services.catalogs import CatalogService
from swissarmybench.services.charts import Cards
from swissarmybench.services.claude import Claude
from swissarmybench.services.code_files import CodeFiles
from swissarmybench.services.codegen import CodeService
from swissarmybench.services.connection_colours import ConnectionColours
from swissarmybench.services.connection_slots import Caller, ConnectionSlots
from swissarmybench.services.connection_swap import ConnectionSwap
from swissarmybench.services.connection_tables import ConnectionTables as ConnectionTablesService
from swissarmybench.services.connection_usage import ConnectionUsage
from swissarmybench.services.connections import ConnectionService
from swissarmybench.services.context_md import ContextMd
from swissarmybench.services.data_export import DataExport
from swissarmybench.services.datasets import ConnectionTables, DatasetService
from swissarmybench.services.debugger import Debugger, DebugKernel
from swissarmybench.services.desktop import Desktop
from swissarmybench.services.explorer import BrowseSources, Explorer, OpenTable
from swissarmybench.services.export import Exports
from swissarmybench.services.extensions import Extensions
from swissarmybench.services.file_dialogs import FileDialogs
from swissarmybench.services.file_watch import FileWatch
from swissarmybench.services.folders import Folders
from swissarmybench.services.found_connections import FoundConnections
from swissarmybench.services.grids import GridService
from swissarmybench.services.hooks import Hooks
from swissarmybench.services.inbox import Inbox
from swissarmybench.services.intellisense import Intellisense
from swissarmybench.services.library import Library
from swissarmybench.services.library_setup import LibrarySetup
from swissarmybench.services.lifecycle import Lifecycle
from swissarmybench.services.lineage import Lineage
from swissarmybench.services.local_api import LocalApi
from swissarmybench.services.modes import Modes
from swissarmybench.services.navigation import Navigation
from swissarmybench.services.ports import INTERACTIVE as PRIORITY_INTERACTIVE
from swissarmybench.services.processes import ProcessRegistry, Sessions
from swissarmybench.services.profile import Profiles
from swissarmybench.services.project_explorer import ProjectExplorer
from swissarmybench.services.project_outline import BothTables, CardPortability, ProjectOutline
from swissarmybench.services.project_scope import ProjectScope
from swissarmybench.services.projects import Projects
from swissarmybench.services.regression import Regression
from swissarmybench.services.relationship_scope import ProjectTables
from swissarmybench.services.relationships import Compares, Finder, KeyFinder, Models
from swissarmybench.services.sab_projects import SabProjects
from swissarmybench.services.sandbox import Sandbox, SandboxAlias, SourcesFrom
from swissarmybench.services.script_export import ScriptExports
from swissarmybench.services.script_ide import ScriptIde
from swissarmybench.services.script_runs import ScriptRuns
from swissarmybench.services.session_log import Heard, SessionLog
from swissarmybench.services.shared_catalog import Here, SharedCatalog
from swissarmybench.services.sharing import Sharing
from swissarmybench.services.snapshots import Snapshots
from swissarmybench.services.sql import SqlBox
from swissarmybench.services.structures import Structures
from swissarmybench.services.table_cells import TableCells
from swissarmybench.services.team import Team
from swissarmybench.services.tieout import TieOut
from swissarmybench.services.timeseries import TimeSeries
from swissarmybench.services.updates import Updates
from swissarmybench.services.variables import Variables
from swissarmybench.services.vault_names import KeptVaultNames, VaultNamesAtStart
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
    file_watch: FileWatch
    code_files: CodeFiles
    grids: GridService
    profiles: Profiles
    analysis: Analysis
    analyze: Analyze
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
    found_connections: FoundConnections
    connection_usage: ConnectionUsage
    connection_slots: ConnectionSlots
    apis: Apis
    structures: Structures
    api_explorer: ApiExplorer
    catalog_loading: CatalogLoading
    vault_names_at_start: VaultNamesAtStart
    connection_tables: ConnectionTablesService
    folders: Folders
    file_dialogs: FileDialogs
    workbench: Workbench
    models: Models
    project_tables: ProjectTables
    finder: Finder
    keys: KeyFinder
    compares: Compares
    tie_out: TieOut
    snapshots: Snapshots
    workbench_window: WorkbenchWindow
    intellisense: Intellisense
    script_ide: ScriptIde
    debugger: Debugger
    table_cells: TableCells
    lineage: Lineage
    projects: Projects
    sab_projects: SabProjects
    project_explorer: ProjectExplorer
    project_scope: ProjectScope
    project_outline: ProjectOutline
    script_exports: ScriptExports
    session_log: SessionLog
    variables: Variables
    explorer: Explorer
    connection_swap: ConnectionSwap
    navigation: Navigation
    connection_colours: ConnectionColours
    library: Library
    library_setup: LibrarySetup
    team: Team
    sharing: Sharing
    sandbox: Sandbox
    local_api: LocalApi
    api_export: ApiExport
    shared_catalog: SharedCatalog
    app_registrations: AppRegistrations
    script_runs: ScriptRuns
    beta: BetaLog
    updates: Updates
    extensions: Extensions
    lifecycle: Lifecycle
    desktop: Desktop
    claude: Claude
    context_md: ContextMd
    live: LiveUpdates
    workers: PriorityWorkers
    # The project modes (the open project's type to its working set) and the extensions that are on
    # (swissarmybench/extensions.py): each one's routes are mounted beside the base's (server/app.py).
    modes: Modes
    switched_on: list[Any]  # the extensions' own modules, each one switched on here
    # What an extension builds its own services from (services/hooks.py: what it hands back), beside the
    # use cases above: the Workbench's documents, a project's files, the export's writer, the run events.
    hooks: Hooks
    data_export: DataExport
    documents: Any
    project_files: Any
    export_writer: Any
    process_event: Callable[..., None]


def usage_documents(
    documents: Documents, hooks: Hooks, sab_projects: SabProjects, project_files: ProjectFiles
) -> list[str]:
    """Where the Connections page looks for a connection's references: with a project open, its own
    notebooks, scripts and apps (everything is the project's, 2026-11-16) and the documents open in a
    Workbench window; with none, the Workbench's recent files and the open documents. Each file once,
    by its real path (one notebook reached by two spellings was listed twice)."""
    paths = list(hooks.documents())
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


def _scaffold_of(project_type: str) -> Any:
    """The scaffold of the extension whose mode is this project type (None: none is on here)."""
    for module in extension_modules.enabled():
        if (getattr(module, "MODE", None) or {}).get("type") == project_type:
            return getattr(module, "scaffold", None)
    return None


# ===== bootstrap's parts, by area (each built once, in bootstrap's order) =====


def _blade_store(settings: Settings, library_folder: LibraryFolder, on_extensions: list[Any]) -> BladeStore:
    """The saved blades: the library's files, the blade folders, the built-in and the extensions' starters."""
    state_dir = settings.state_dir
    return BladeStore(
        library_folder.root,
        made=library_folder.ensure,
        folders_file=state_dir / "blade_folders.json",
        pins_file=state_dir / "blade_pins.json",
        # The built-in starter pack ships inside the package, so each version brings its own.
        starters=Path(__file__).resolve().parent / "starters",
        # Each extension that is on: its own starters (its module's STARTERS folder).
        more_starters=lambda: [Path(s) for m in on_extensions if (s := getattr(m, "STARTERS", None))],
        # A connection's tables are always listed: one saved with no listing query gets its starter's.
        listing=lambda b: blade_tables.listing_for(b.kind, b.template, b.dialect, TEMPLATES),
    )


def _given_out(kept_vault_names: KeptVaultNames, blade_store: BladeStore, job: dict[str, Any]) -> None:
    """A vault that loads every secret: its names as given out here (no variable twice, a taken one
    prefixed), the ones it lists now given out the same way (`yours`, `kept`: a kernel's load)."""
    job["yours"] = sorted(kept_vault_names.defined())
    for vault in job.get("vaults") or []:
        if isinstance(vault, dict) and vault.get("every"):
            label = str(vault.get("label") or "")
            vault["kept"] = kept_vault_names.kept_of(label)
            try:
                vault["mapping"] = kept_vault_names.mapping(blade_store.get(label)) | dict(vault["mapping"])
            except KeyError:
                pass


async def _vault_values(
    blade_store: BladeStore, seconds: float, wanted: dict[str, dict[str, str]]
) -> tuple[dict[str, str], list[str]]:
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
            seconds,
        )
    except (python_connections.PythonConnectionError, blade_runner.RefreshError) as error:
        return {}, [str(error)]
    values = {str(k): str(v) for k, v in dict(answer.get("values") or {}).items()}
    return values, [str(p) for p in answer.get("problems") or []]


def _secrets_of(blade_store: BladeStore, name: str) -> list[str] | None:
    """A connection's or blade's passwords by the names its code asks secret() for (None: none here)."""
    try:
        return blade_store.get(name).secrets
    except KeyError:
        return None


def _files_of(blade_store: BladeStore, name: str) -> list[str]:
    """A connection's certificate and keystore files read from a variable: those variables."""
    try:
        return [m["variable"] for m in env_settings(blade_store.get(name).code)]
    except KeyError:
        return []


def _workspace(
    settings: Settings,
    port: int,
    token: str,
    store: DatasetStore,
    connection: Any,
    live: LiveUpdates,
    workers: PriorityWorkers,
    session_log: SessionLog,
    audit_log: bool,
) -> Workspace:
    """The workspace: the ports every use case shares."""
    state_dir = settings.state_dir
    return Workspace(
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
        grammar=grammar_later(),  # read from DuckDB on the first query, not at start
        interrupted=duckdb.InterruptException,
        engine_error=duckdb.Error,
    )


def _beta_log(ws: Workspace, settings: Settings, store: DatasetStore, token: str, audit_log: bool) -> BetaLog:
    """The beta log: errors, slow requests, processes, page errors and notes, redacted (written only where
    the audit log is; beta mode on or off is beta.json, SWISSARMYBENCH_BETA wins)."""
    state_dir = settings.state_dir
    return BetaLog(
        ws,
        BetaFiles(state_dir / "logs" if audit_log else None, settings.beta_log_bytes, settings.beta_log_days),
        BetaSwitch(state_dir / "beta.json" if audit_log else None),
        variable=os.environ.get("SWISSARMYBENCH_BETA", ""),
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
    on_extensions = extension_modules.enabled()

    # ===== the adapters =====
    connection = open_database(settings.duckdb_memory_limit)
    workers = PriorityWorkers(settings.worker_threads)
    store = DatasetStore(
        connection, settings.max_dataset_bytes, settings.max_total_bytes, settings.max_datasets
    )
    live = LiveUpdates()
    # The library (Plans/library.plan.md): this computer's connections, APIs, vaults, blades, relationship
    # sets, variables and colours, in one folder made to be a Git repository, whatever project is open;
    # Settings points it elsewhere (library.json: the path only). README.md and .gitignore made on first use.
    library_folder = LibraryFolder(settings.library_dir, state_dir / "library.json" if audit_log else None)
    # A key vault's secret names as last read here (the library's local/vault-names/: names only, never a
    # value): a vault that loads every secret gives its variables from the first second after a start.
    kept_vault_names = KeptVaultNames(
        VaultNameFiles((lambda: library_folder.root) if audit_log else None, library_folder.ensure),
        lambda: datetime.now(UTC).isoformat(timespec="seconds"),
    )
    blade_store = _blade_store(settings, library_folder, on_extensions)
    verifier = Verifier(settings.duckdb_memory_limit)

    def process_event(
        kind: str, event: str, code: int | None, seconds: float | None, reason: str = ""
    ) -> None:
        beta.process(kind, event, code, seconds, reason)

    async def run_blade(
        blade: Blade, mode: str, typed: dict[str, str], extra: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        job = blade_runner.payload(blade_store, blade, mode, typed, extra)
        given_out(job)
        kind = "catalog" if mode == "catalog" else "blade"

        async def work() -> dict[str, Any]:
            return await blade_runner.run(
                job, settings.blade_timeout_seconds, report=lambda *e: process_event(kind, *e)
            )

        # A connection's run through the app (a catalog load, a table read, a query, a test) is a call
        # the Connections page counts (services/connection_usage.py; memory only); each waits for one of the
        # connection's slots first (services/connection_slots.py), and gives it back however it ends.
        try:
            if blade.kind in ("sql", "other") and mode in slot_rules.KINDS:
                more = extra or {}
                place: dict[str, Any] = more["place"] if isinstance(more.get("place"), dict) else {}
                sql = more.get("sql") or "\n;\n".join(";\n".join(a) for a in more.get("attempts") or [])
                answer = await slots.run(
                    blade.name,
                    work,
                    kind=mode,
                    targets=(str(place.get("table") or ""),),
                    sql=str(sql or ""),
                    dialect=str(blade.dialect or ""),
                )
            else:
                answer = await work()
        except Exception as error:
            connection_usage.record(blade.name, mode, ok=False, error=str(error))
            raise
        about = answer.get("about") if isinstance(answer, dict) else None
        connection_usage.record(blade.name, mode, ok=True, about=about if isinstance(about, dict) else None)
        return answer

    async def stream_blade(
        blade: Blade,
        typed: dict[str, str],
        filename: str,
        on_output: Callable[[str, str], None],
        started: Callable[[Callable[[], None]], None],
    ) -> dict[str, Any]:
        """The blade IDE's Run: the blade (its code the editor's) in a child process, its output streamed."""
        job = blade_runner.payload(blade_store, blade, "run", typed)
        given_out(job)
        # The code's own lines under a name the error panel reads as your file (never the .blade.py itself,
        # whose lines start after its header).
        job["filename"] = os.path.join(tempfile.gettempdir(), "swissarmybench-blades", filename)
        answer = await blade_runner.run_streaming(
            job,
            settings.blade_timeout_seconds,
            on_output,
            started,
            report=lambda *e: process_event("blade", *e),
        )
        connection_usage.record(
            blade.name, "test", ok=bool(answer.get("ok")), error=str(answer.get("failed") or "")
        )
        return answer

    given_out = partial(_given_out, kept_vault_names, blade_store)
    vault_values = partial(_vault_values, blade_store, settings.vault_timeout_seconds)
    secrets_of = partial(_secrets_of, blade_store)
    files_of = partial(_files_of, blade_store)

    async def vault_environment() -> tuple[dict[str, str], list[str]]:
        """Every vault's entries for a Workbench kernel about to start, and the vaults that failed."""
        job = blade_runner.load_payload(blade_store)
        if job is None:
            return {}, []
        given_out(job)
        try:
            answer = await blade_runner.run(job, settings.vault_timeout_seconds)
        except blade_runner.RefreshError as error:
            why = str(error)
            if "did not finish" in why:
                seconds = settings.vault_timeout_seconds
                why = f"Reading the vaults took over {seconds:.0f} seconds: this kernel started without them."
            return {}, [why]
        values = {str(k): str(v) for k, v in dict(answer.get("values") or {}).items()}
        # A vault that loads every secret: the names it listed, kept (names only).
        for vault, listed in dict(answer.get("names") or {}).items():
            if isinstance(listed, list):
                await blades.keep_names(str(vault), connection_rules.vault_names(listed))
        return values, [str(p) for p in answer.get("problems") or []]

    # ===== the workspace: the ports every use case shares =====
    session_log = SessionLog(live, JsonFile(state_dir / "follow.json" if audit_log else None))
    ws = _workspace(settings, port, token, store, connection, live, workers, session_log, audit_log)

    # ===== the beta log: errors, slow requests, processes, page errors and notes, redacted =====
    # (written only where the audit log is; beta mode on or off is beta.json, SWISSARMYBENCH_BETA wins)
    # Read each time: the Variables page's values join the environment as they are added.
    beta = _beta_log(ws, settings, store, token, audit_log)

    # ===== the services =====
    processes = ProcessRegistry()  # the Python sessions offering tables to the Open list
    tickets = ExportTickets()  # the agent exports the user approved, not yet written
    # The questions for the user that the agent's requests wait on (the page's approval prompt): one
    # for every use case that writes the user's rows to disk for the agent.
    approvals = Approvals(live)
    # How many queries run at once on each connection, the agent's share and the line (the owner,
    # 2026-11-21): the one gate run_blade passes through; a kernel's slot is leased by its routes.
    slots = ConnectionSlots(
        live,
        ws.audit,
        limits_of=lambda name: slot_rules.limits_of_header(blade_store.get(name).queries),
        save_limits=lambda name, header: blade_store.set_header(name, {"queries": header}).name,
        ask=approvals.ask,
    )
    datasets = DatasetService(
        ws,
        table_reader,
        processes,
        own_file=lambda path: is_own_file(path, state_dir, export_dir),
        on_shutdown=on_shutdown or (lambda: None),
    )
    # A table read from a file is watched: changed on disk, the page says so (Reload, Not now).
    file_watch = FileWatch(ws, datasets.origins.get, file_stamp, settings.file_watch_seconds)
    datasets.changed_on_disk = file_watch.changed
    datasets.not_now = file_watch.not_now
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
        reveal=lambda path: file_manager.reveal(path),  # Show its file (looked up when clicked)
        kept_names=kept_vault_names,
        stream_blade=stream_blade,
    )
    # The blade IDE's Open as grid: a run's table in a tab of its own.
    blades.open_table = lambda name, table, who: datasets.store_table(
        datasets.free_name(name), table, "blade", True, who
    )
    catalog_loading = CatalogLoading(
        ws, blades, catalogs, settings.auto_load_catalogs, settings.catalogs_at_once, live.windows
    )
    # A vault that loads every secret: its names read again once the first window is open (kept meanwhile).
    vault_names_at_start = VaultNamesAtStart(
        blades,
        kept_vault_names,
        live.broadcast,
        settings.auto_read_vaults,
        settings.catalogs_at_once,
        live.windows,
    )
    # Relationship sets come from the person's own folder and the shared folders, which are the blade
    # folders: one team folder carries blades and sets alike.
    compares = Compares(ws)
    models = Models(
        ws,
        ModelFiles(
            state_dir,
            shared=lambda: [f["path"] for f in blade_store.folders() if f["exists"]],
            library=lambda: library_folder.root,
            made=library_folder.ensure,
        ),
        approvals,
    )
    datasets.renamed.append(models.rename_table)
    documents = Documents(state_dir / "recent.json", settings.workbench_dir)
    script_runs = ScriptRuns(
        ws,
        JsonFile(state_dir / "run_settings.json" if audit_log else None),
        documents,
        secrets_of=secrets_of,
        files_of=files_of,
    )
    table_cells = TableCells(
        ws,
        datasets.origins,
        table_reader.query_to_arrow_stream,  # type: ignore[arg-type]
        table_reader.planned_arrow_stream,  # type: ignore[arg-type]
    )
    project_files = ProjectFiles()
    # What the extensions that are on hand back once they are built (services/hooks.py): the documents the
    # Workbench windows hold, what stops with a kernel or a window, a canvas, an app's file.
    hooks = Hooks()
    data_export = DataExport(
        project_files,
        table_cells.arrange,
        lambda path: hooks.held(path),
        lambda folder: project_scope.edited_in(folder),  # data.py edited by hand: kept (Scripts IDE)
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
        hooks=hooks,
    )

    def kernel_caller(kernel: str) -> Caller:
        role, words = workbench.runner_of(kernel)
        document = workbench.document_of(kernel)  # Open its source: the document in the Workbench
        source = {"document": document} if document else {}
        return Caller(role, "The agent" if role == "agent" else words, kernel=kernel, source=source)

    async def kernel_ended(kernel: str) -> None:
        slots.kernel_stopped(kernel)  # its slots go back at once

    slots.kernel_caller = kernel_caller
    slots.interrupt_kernel = workbench.interrupt
    workbench.set_kernel_stopped(kernel_ended)
    # Each connection's colour: the library's colours.toml, the same in every project; never one of the
    # rail's (the kind colours, the accent).
    connection_colours = ConnectionColours(
        ws,
        blades,
        ColoursFile(
            (lambda: library_folder.root / library_rules.COLOURS_FILE) if audit_log else None,
            library_folder.ensure,
        ),
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
        documents=lambda: usage_documents(documents, hooks, sab_projects, project_files),
        read=documents.read,
        origin_of=datasets.origins.get,
        environ=os.environ,
        now=time.time,
    )
    # Add API: the library's apis/<name>/: API_<name>.py, its API blade and web call blades.
    api_library = ApiLibrary(lambda: library_folder.root / library_rules.APIS, library_folder.ensure)
    apis = Apis(
        ws,
        ApiFiles(),
        SpecSource(),
        connections,
        api_library,
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
        export_data=data_export.export_data,
        project_app=lambda name: hooks.project_app(name),
        remember=lambda path: documents.remember(path, time.time()),
        approvals=approvals,
        scaffold=_scaffold_of,
    )
    # A project is a folder: its .sab/ state written beside its files.
    archive = SabArchive(settings.max_project_entries, settings.max_project_read_bytes)

    async def use_project(folder: str | None) -> None:
        """The open project's saved dashboards (its .sab/visualizations), or this computer's with none open.
        Connections, APIs, vaults, blades and variables are the library's, whatever is open."""
        app = Path(folder) / APP_FOLDER if folder else None
        dashboards.folder = app / "visualizations" if app else state_dir / "dashboards"
        await catalog_loading.rescope()
        await variables.rescope()
        await live.broadcast({"type": "blades_changed"})
        if structures_ready:
            await structures_ready[0].project_changed(folder)  # the closed project's structures go with it

    structures_ready: list[Structures] = []  # set once built (below): use_project is made before it

    async def library_moved() -> None:
        """Settings' Library folder changed: every store reads the new folder (the pages told)."""
        blade_store.use(library_folder.root)
        await catalog_loading.rescope()
        await variables.rescope()
        await live.broadcast({"type": "blades_changed"})
        await live.broadcast({"type": "connection_colours_changed"} | connection_colours.get())
        if shared_ready:
            shared_ready[0].load()  # the new folder's catalog/
            await live.broadcast({"type": "catalog_changed", "from": "folder", "changed": 0})
        if setup_ready:
            setup_ready[0].forget()
        counts = library_folder.counts()
        said = setup_rules.setup_notice(counts["connections"], counts["vaults"])
        if said:  # a team's meta store, pointed at: what this computer needs is on Settings' checklist
            await live.broadcast({"type": "library_notice", "text": said})

    setup_ready: list[LibrarySetup] = []  # set once built (below)

    shared_ready: list[SharedCatalog] = []  # set once built (below)

    library = Library(ws, library_folder, blade_store, approvals, library_moved)

    recent_projects = RecentProjects(state_dir / "recent_projects.json" if audit_log else None)
    explorer_ready: list[ProjectExplorer] = []  # set once built (below): the projects folder New uses
    sab_projects = SabProjects(
        ws,
        archive,
        recent_projects,
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
        adopt=library.adopt_project,
        autosave_seconds=settings.autosave_seconds,
        projects_folder=lambda: explorer_ready[0].folder() if explorer_ready else str(settings.projects_dir),
    )
    # The Project Explorer (the home page): every project in one place, sortable, the types explained.
    project_explorer = ProjectExplorer(
        ws,
        ExplorerFiles(file_manager.show, file_manager.trash),
        ExplorerSettings(state_dir / "projects.json" if audit_log else None),
        recent_projects,
        sab_projects,
        approvals,
        default_folder=str(settings.projects_dir),
        modes=extension_modules.modes,
        streamlit=extension_modules.STREAMLIT_KIND,
        off=lambda: {
            str(e["project_type"]): e
            for e in extension_rules.off_project_types(extension_rules.CATALOG, extension_modules.modes())
        },
    )
    explorer_ready.append(project_explorer)
    sab_projects.shared_folder = project_explorer.shared_folder
    # Structures: nested data (JSON, YAML, XML, TOML) as documents; the project's own in structures/.
    structures = Structures(
        ws,
        StructureFiles(),
        StructureCodecs(),
        datasets,
        rows_to_table,
        project_folder=lambda: sab_projects.current.folder if sab_projects.current else None,
        default_folder=documents.made_default_folder,
        documents=lambda: usage_documents(documents, hooks, sab_projects, project_files),
        read_document=documents.read,
    )
    structures_ready.append(structures)
    # The APIs page: the library's APIs explored; a call sent opens in Structures, its origin the call.
    api_explorer = ApiExplorer(
        ws,
        apis,
        api_library,
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
        ws,
        connections,
        catalogs,
        catalog_loading,
        table_reader.table_to_arrow_stream,
        aliases=lambda: (
            hooks.dataset_aliases() | ({sandbox_rules.NAME: sandbox_alias} if sandbox.folder() else {})
        ),
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
        open_documents=lambda: hooks.documents(),
        ask_window=lambda command, args: workbench_window.ask(command, args, "app"),
    )

    # The tables the open project uses: the ERD draws only those by default (the owner, 2026-11-17).
    def project_documents() -> tuple[set[str], list[tuple[str, str]]] | None:
        project = sab_projects.state().get("project")
        if not project:
            return None
        names = {str(t["name"]) for t in project.get("tables", [])}
        texts: list[tuple[str, str]] = []
        for path in usage_documents(documents, hooks, sab_projects, project_files):
            try:
                text, full, _ = documents.read(path)
            except (OSError, ValueError):
                continue
            texts.append((full, text))
        return names, texts

    project_tables = ProjectTables(models, project_documents)
    # A connection deleted: the relationships its tables held go from the ones in use (saved sets stay).
    blades.connection_removed.append(
        lambda name, who: models.forget_connection(name, set(connection_swap.tables_of(name)), who)
    )

    # The shared catalog (the owner, 2026-11-17): the library's catalog/<connection>.json, kept by what
    # happens here and read again when the user's pulls change it. The app never runs git.
    def connections_here() -> list[Here]:
        found = []
        for blade in blade_store.all():
            if blade.web_call or connection_rules.connection_kind(blade.kind, blade.template) is None:
                continue
            kind = connection_table_rules.tables_kind(
                blade.kind, blade.template, blade.dialect, blade.catalog_language, blade.tags, blade.code
            )
            if kind is not None:  # never a key vault: it has no tables
                found.append(Here(blade.name, kind, str(blade.template or "")))
        return found

    def project_use() -> tuple[str, set[str], list[tuple[str, str]]] | None:
        project = sab_projects.state().get("project")
        found = project_documents()
        if not project or found is None:
            return None
        folder = str(project.get("folder") or "")
        name = Path(folder).name if folder else str(project.get("name") or "")
        names, texts = found
        return name, names | {i.name for i in store.all()}, texts

    shared_catalog = SharedCatalog(
        ws,
        CatalogFiles((lambda: library_folder.root) if audit_log else None, library_folder.ensure),
        connections_here,
        catalogs.listing_rows,
        lambda: models.model,
        today=lambda: datetime.now(UTC).date().isoformat(),
        now=lambda: datetime.now(UTC).isoformat(timespec="seconds"),
        project=project_use,
    )
    shared_ready.append(shared_catalog)
    shared_catalog.load()
    library.catalog_info = shared_catalog.info
    project_tables.shared = shared_catalog.model

    async def connection_saved(blade: Any) -> None:
        await shared_catalog.saved(blade.name)

    blades.blade_saved.append(connection_saved)
    blades.tables_listed.append(shared_catalog.listed)
    blades.connection_removed.append(shared_catalog.removed)
    models.listeners.append(shared_catalog.relationships)
    sab_projects.saved.append(shared_catalog.project_used)

    async def project_opened(folder: str, _extra: Any) -> None:
        await shared_catalog.project_used(folder)

    sab_projects.opened.append(project_opened)
    # Code files that update themselves everywhere (services/code_files.py): the open project's and the
    # library's.
    code_files = CodeFiles(
        ws,
        lambda: (
            sab_projects.current.folder if sab_projects.current else None,
            str(library_folder.root) if audit_log else None,
        ),
        code_file_disk.stamp,
        code_file_disk.file_hash,
        code_file_disk.code_files_in,
        code_file_disk.resolve,
        settings.file_watch_seconds,
    )
    project_scope = ProjectScope(sab_projects, archive, library, connections, on_saved=catalog_loading.saved)
    code_files.listeners.append(project_scope.saw)  # a made file saved by hand is marked so
    # The Variables page: this computer's variables (never a project's): the shareable file and the local
    # values; their values given to this server's environment, so what it runs and starts reads them.
    variables_file = VariableFiles(
        (lambda: library_folder.root) if audit_log else None, library_folder.ensure
    )
    if audit_log:
        # Once: this computer's stores from before the library, written as library files (said on the page).
        moved = library_folder.migrate(
            state_dir, blade_store, variables_file, datetime.now(UTC).date().isoformat()
        )
        library.notice("computer", library_rules.computer_migration_words(moved["moved"], moved["backup"]))
        # Once: the library's tangs/ (the old name, 2026-11-17) as relationship-sets/ (said on the page).
        sets = library_folder.move_relationship_sets(state_dir, datetime.now(UTC).date().isoformat())
        library.notice("computer", library_rules.sets_migration_words(sets["moved"], sets["backup"]))

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
        documents=lambda: usage_documents(documents, hooks, sab_projects, project_files),
        read=documents.read,
        run_settings=script_runs,
        kernels=workbench.kernel_count,
        vault_values=vault_values,
        remembered=blades.remembered,
        renamed_notes=kept_vault_names.notes,
    )
    # One name, one variable: the vaults' names given out around the user's own variables.
    kept_vault_names.vaults = blade_store.all
    kept_vault_names.defined = variables.defined_names
    connections.variable_check = variables  # a Test's ${NAME} checked first (12.7)
    # Find connections on this computer (the owner, 2026-11-20): the known tools' files and the hint scan of
    # the app settings folders, read-only, on the user's click; never this app's own state folder or library.
    found_connections = FoundConnections(
        ws,
        ConnectionFinder(
            home=settings.find_home,
            system=settings.find_system,
            skip=lambda: (state_dir, library_folder.root),
        ),
        TEMPLATES,
        blades,
        lambda data, who: connections.save(data, None, who),
        variables,
        approvals,
    )

    def every_connection() -> list[tuple[str, str, str]]:
        """(name, kind, code) of each connection: an app registration's users (they read its variables)."""
        out = []
        for row in connections.listing()["connections"]:
            try:
                blade = blade_store.get(str(row["name"]))
            except Exception:  # noqa: S112 (one that cannot be read is not counted)
                continue
            kind = "powerbi" if blade.dialect == "dax" else str(blade.template or row.get("connection") or "")
            out.append((blade.name, "sqlserver" if kind == "azuresql" else kind, blade.code))
        return out

    app_registrations = AppRegistrations(
        ws,
        RegistrationFiles(lambda: library_folder.root, library_folder.ensure),
        MicrosoftProbe(),
        variables.values,
        every_connection,
    )
    app_registrations.tables_of = catalogs.places  # Azure SQL's SELECT TOP 0 on its catalog's tables
    datasets.variables = variables  # a query's ${NAME}: a bound parameter; a path's, read here
    structures.variables = variables
    api_explorer.variables = variables
    if audit_log:
        # Once (12.7: a password field holds ${NAME}): each connection's own saved password becomes a keyring
        # variable, its connection's file backed up first; then what saved text now reads a variable (once).
        today = datetime.now(UTC).date().isoformat()
        passwords_moved = JsonFile(state_dir / "variables_moved.json")  # once: the first start with 12.7
        if passwords_moved.read() is None:
            library.notice(
                "computer",
                variables.migrate_passwords(
                    backup_copies(state_dir / "backup" / f"before-variables-{today}")
                ),
            )
            passwords_moved.write({"moved": today})
        refs_seen = JsonFile(state_dir / "variable_refs.json")
        holding = variables.holding() if refs_seen.read() is None else []
        if holding:  # said once; nothing found writes nothing
            library.notice("computer", variable_rules.holding_words(holding))
            refs_seen.write({"listed": today})

    # Set up from the meta store: what this computer needs before the team's connections work.
    library_setup = LibrarySetup(
        ws,
        blades,
        blade_store.secret_status,
        lambda: variables.listing()["variables"],
        connections,
    )
    setup_ready.append(library_setup)

    # Shared projects (the owner, 2026-11-18: "local projects and shared projects"): the connections a
    # project's documents name, said once when a shared one's only work here, and on the checklist when not
    # set up here.
    def connections_named_in(folder: str) -> list[str]:
        names = list(dict.fromkeys([h.name for h in connections_here()] + list(shared_catalog.catalogs())))
        texts = []
        for path in sorted(Path(folder).glob("*")):
            if path.suffix.lower() in (".ipynb", ".py") and path.is_file():
                try:
                    texts.append((str(path), path.name, path.read_text(encoding="utf-8")))
                except (OSError, UnicodeDecodeError):
                    continue
        found = []
        for name in names:
            for full, title, text in texts:
                try:
                    if usage_rules.document_references(full, title, text, name):
                        found.append(name)
                        break
                except ValueError:
                    continue
        return found

    async def shared_projects(not_working: set[str]) -> list[setup_rules.SharedProject]:
        folder = project_explorer.shared_folder()
        if not folder:
            return []
        here = {h.name.casefold() for h in connections_here()}
        out = []
        for path in await asyncio.to_thread(ExplorerFiles.scan, folder):
            named = await asyncio.to_thread(connections_named_in, path)
            missing = [n for n in named if n.casefold() not in here or n.casefold() in not_working]
            out.append(setup_rules.SharedProject(Path(path).name, path, tuple(missing)))
        return out

    library_setup.shared_projects = shared_projects

    async def shared_opened(folder: str, _extra: Any) -> None:
        """A shared project opened (or made): its connections that only work on this machine, said once."""
        if project_explorer.where(folder) != "shared":
            return
        local = 0
        for name in await asyncio.to_thread(connections_named_in, folder):
            try:
                blade = blade_store.get(name)
                status = blade_store.secret_status(blade)
            except Exception:  # noqa: S112 (a teammate's connection not here: the checklist says so)
                continue
            sources = ["keyring" if status.get(s) else "" for s in blade.secrets]
            local += bool(portability_rules.check(blade.code, blade.template, sources))
        said = explorer_rules_words(local)
        if said:
            library.notice("project", said)
            await live.broadcast({"type": "library_notice", "text": said})

    sab_projects.opened.append(shared_opened)

    # The Data Explorer: one search over the connections and their catalogs, the open tables, the
    # variables and the blades, Structures' documents and paths, APIs' web calls that return a table.
    # The Data page browses the same sources: each connection's tree (never loaded by a look: Load does).
    explorer = Explorer(
        ws,
        BrowseSources(
            lambda: connections.listing()["connections"],
            lambda name: connection_tables.tree(name, load=False),
            connection_tables.describe,
        ),
    )
    explorer.register(
        "connections",
        explorer_providers.connections_provider(
            lambda: connections.listing()["connections"], catalogs, catalog_loading.state
        ),
    )

    def open_tables() -> list[OpenTable]:
        out = []
        for info in store.all():
            grids = ws.grids.for_dataset(info.name)
            out.append(
                OpenTable(
                    info.name,
                    info.row_count,
                    [(c.name, c.type) for c in info.columns],
                    grids[0].id if grids else None,
                    datasets.origins.get(info.name),
                )
            )
        return out

    explorer.register("grids", explorer_providers.grids_provider(open_tables))
    explorer.register(
        "shared",
        explorer_providers.shared_catalog_provider(
            lambda: list(shared_catalog.tables()), catalogs.loaded_names, shared_catalog.here_names
        ),
    )
    explorer.register(
        "variables", explorer_providers.variables_provider(lambda: variables.listing()["variables"])
    )
    explorer.register("blades", explorer_providers.blades_provider(lambda: blades.listing()["blades"]))
    explorer.register(
        "structures",
        explorer_providers.structures_provider(structures.listing, lambda sid: structures.node(sid)),
    )
    explorer.register("apis", explorer_providers.apis_provider(lambda: blades.listing()["blades"]))

    # The project's sandbox (domain/sandbox.py): the data a local sandbox API reads and writes, mocked as the
    # client of the connection each table came from; [Sandbox].orders in DuckDB SQL; a section in the Catalog.
    def sandbox_client(table: str | None, connection: str | None) -> dict[str, Any]:
        name = connection
        if name is None and table is not None:
            name = datasets.origins.get(table).connection
        if not name:
            return {"kind": sandbox_rules.PLAIN}
        try:
            blade, _ = connections.blade(name)
            saved, tables_kind = connection_tables.kind(name)
        except Exception:
            return {"kind": sandbox_rules.PLAIN, "connection": name}
        return {
            "kind": tables_kind,
            "connection": saved,
            "template": blade.template or "",
            "dialect": blade.dialect or "",
        }

    async def sandbox_grid_view(name: str) -> Any:
        body = await table_cells.view(name)
        return table_reader.arrow_stream_to_table(body, settings.max_dataset_bytes)

    async def sandbox_connection_table(name: str, place: Place) -> Any:
        kept, _ = await connection_tables.read(name, place)
        return kept.read.table

    async def sandbox_show(name: str, table: Any, follow: bool, words: str) -> dict[str, Any]:
        # Its origin: the sandbox table (its lineage and its read-only cell's load name [Sandbox].<table>).
        table_name = name.removeprefix(sandbox_rules.GRID_PREFIX)
        sql = f"SELECT * FROM [{sandbox_rules.NAME}].{table_name}"  # noqa: S608 (a checked table name)
        origin = TableOrigin("sandbox", connection=sandbox_rules.NAME, sql=sql, filename=words)
        return await datasets.store_table(name, table, "sandbox", False, "user", follow=follow, origin=origin)

    async def sandbox_view_rows(name: str, places: list[int]) -> tuple[list[str], list[list[Any] | None]]:
        """An open sandbox grid's view rows at these places (its steps applied): what an edit names."""
        grid, info = ws.grids.first_for(name), ws.store.get(name)
        if grid is None or info is None:
            raise LookupError(f"{name} is not open in Grids.")

        def read(cursor: Any) -> tuple[list[str], list[list[Any] | None]]:
            shown: list[str] = []
            out: list[list[Any] | None] = []
            for place in places:
                window = ws.views.window(cursor, info, grid.steps, grid.settings, place, place + 1, None)
                shown = [c.name for c in window.columns]
                out.append(list(window.rows[0]) if window.rows else None)
            return shown, out

        return await ws.grid_query(grid, None, PRIORITY_INTERACTIVE, read)

    def sandbox_connections() -> list[str]:
        """Mocked as's choices: the saved connections that have tables."""
        out = []
        for c in connections.listing()["connections"]:
            try:
                connection_tables.kind(str(c["name"]))
            except Exception:  # noqa: S112 (no tables: not a connection to mock)
                continue
            out.append(str(c["name"]))
        return sorted(out, key=str.casefold)

    def sandbox_key(connection: str, place: Place) -> list[str]:
        """A connection's table's primary key as the shared catalog knows it ([]: not known)."""
        for name in (".".join(p for p in (place.schema, place.table) if p), place.table):
            try:
                return [str(c) for c in shared_catalog.table(connection, name).get("primary_key") or []]
            except (LookupError, ValueError):
                continue
        return []

    def sandbox_ignore(folder: str) -> None:
        archive.write_state(folder, APP_IGNORE_FILE, APP_GITIGNORE.encode("utf-8"))

    sandbox = Sandbox(
        ws,
        lambda: sab_projects.current.folder if sab_projects.current is not None else None,
        SandboxFiles,
        SourcesFrom(
            sandbox_grid_view,
            sandbox_connection_table,
            datasets.read_file,
            sandbox_show,
            sandbox_client,
            structure_fn=structures.records_table,
            view_rows_fn=sandbox_view_rows,
            connections_fn=sandbox_connections,
            key_fn=sandbox_key,
        ),
        approvals,
        lambda sql: duckdb_grammar().parse(sql),
        ignore=sandbox_ignore,
    )
    sandbox_alias = SandboxAlias(sandbox)
    # The Sandbox as a connection (the owner, 2026-11-21): its card on the Connections page and its colour.
    connection_usage.extra_cards = lambda: [c for c in [sandbox.card()] if c is not None]
    connection_colours.fixed = lambda: (
        [(sandbox_rules.NAME, sandbox_rules.COLOUR)] if sandbox.folder() else []
    )
    # The project's local sandbox API (API.py): hosted in a process of its own that gets only the sandbox.
    local_api = LocalApi(
        ws,
        sandbox.folder,
        LocalApiFiles(),
        api_runs.start,
        sandbox,
        approvals,
        data_url=lambda key: f"http://127.0.0.1:{port}/sandbox/data/{key}",
    )
    explorer.register("sandbox", explorer_providers.sandbox_provider(sandbox.names_and_columns))

    async def open_work() -> dict[str, Any]:
        """What is open and what an update would lose: the tables, the Workbench
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
        titles = [str(d["title"]) for d in documents if d["unsaved"]] + hooks.unsaved()
        return {
            "tables": tables,
            "documents": documents,
            "unsaved": list(dict.fromkeys(titles)),
            "kernels": workbench.kernel_count(),
        }

    # The update check (the one request that leaves the computer, the owner's call) and Update to X.
    failure_note = state_dir / "update_failed.json" if audit_log else None
    # Extensions (the Extensions page): the installed ones found once, at start; Install and Remove hand
    # over to the update's helper, and each update keeps the installed ones (`--with`).
    update_helper = UpdateHelper(info_file_path(), state_dir / "update_failed.json")
    extensions = Extensions(
        current=__version__,
        found=discover_extensions(os.environ),
        helper=update_helper,
        approvals=approvals,
        audit=ws.audit,
        live=live,
        stop=on_shutdown or (lambda: None),
        record=JsonFile(state_dir / "extensions.json" if audit_log else None),
        panels={
            str(getattr(m, "ID", "")).lower(): str(m.PANEL)
            for m in on_extensions
            if isinstance(getattr(m, "PANEL", None), str) and str(m.PANEL).startswith("/")
        },
    )
    update_helper.kept = extensions.kept_wheels
    # Settings' Team box: one GitHub repository for the team library and its projects/ (team.json: the team
    # joined, the folders before it, a step kept over Install's restart). The GitHub work is an extension's.
    syncing = next((e for e in extension_rules.CATALOG if "team" in e.provides), None)
    team = Team(
        ws,
        hooks,
        library,
        project_explorer,
        library_setup,
        JsonFile(state_dir / "team.json" if audit_log else None),
        TeamFiles(file_manager.show),
        str(state_dir),
        approvals,
        lambda: {
            "id": syncing.id if syncing else "",
            "name": syncing.name if syncing else "",
            "installable": extensions.state()["installable"],
        },
    )
    # Share a running app with your organization (Microsoft Dev Tunnels; the third way data leaves this
    # computer, on the user's click): devtunnel in the state folder's devtunnel/, got on the first share.
    sharing = Sharing(
        ws,
        DevTunnelProgram(TunnelFiles(state_dir / "devtunnel")),
        lambda: hooks.share_targets,
        approvals,
        port,
    )
    hooks.sharing = sharing
    updates = Updates(
        current=__version__,
        feeds=settings.update_feeds,
        feed=HttpFeed(),
        switch=UpdateSwitchFile(state_dir / "update.json" if audit_log else None),
        helper=update_helper,
        open_work=open_work,
        approvals=approvals,
        audit=ws.audit,
        live=live,
        stop=on_shutdown or (lambda: None),
        failed=take_failure_note(failure_note),
        changing=extensions.changing,
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

    # One Jedi world and one set of linters: the editors' intelligence's, and the Scripts IDE's (never a
    # second).
    jedi_world = JediWorld()
    linters = Linters(run_text)
    intellisense = Intellisense(
        ws,
        kernel_intel.answer,
        jedi_world,
        ProjectModules(),
        linters,
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
    script_ide = ScriptIde(
        ws,
        ScriptCode(run_text),
        jedi_world,
        linters,
        tree=lambda: project_scope.tree("scripts"),
        touched=code_files.touched,
        library=lambda: (
            (str(library_folder.root), code_file_disk.code_files_in(str(library_folder.root)))
            if audit_log
            else (None, [])
        ),
        tables=table_cells.listing,
        trash=file_manager.trash,  # Delete: the system's trash, the user's own
        library_roots=lambda: tuple(  # Python's own folders: a library's source, read-only
            dict.fromkeys(
                p
                for k in ("stdlib", "platstdlib", "purelib", "platlib")
                if (p := sysconfig.get_paths().get(k))
            )
        ),
    )
    blades.lint = intellisense.lint  # the blade IDE's Problems, for the agent (blades_problems)
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
        shared=lambda: shared_catalog.listing(),
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
    context_md.access = app_registrations.access
    modes = Modes(
        extension_modules.modes,
        lambda: sab_projects.current.folder if sab_projects.current is not None else projects.opened,
        projects.type_of,
        extension_modules.areas,
        sab_projects.setting,
        sab_projects.set_setting,
    )
    context_md.gates = modes.gates

    def saved_dashboards() -> list[dict[str, Any]]:
        """The open project's saved dashboards: each one's name and its last version's cards."""
        out = []
        for listed in dashboards.names():
            body = dashboards.read(str(listed["name"])) or {"versions": []}
            last = body["versions"][-1] if body["versions"] else {}
            out.append({"name": listed["name"], "cards": last.get("cards") or []})
        return out

    # The project's outline, ARCHITECTURE.md: its two seams wired to the ERD's tables in the project
    # (services/relationship_scope.py) and the connection cards' portability (domain/portability.py).
    project_outline = ProjectOutline(
        ws,
        archive,
        project=lambda: sab_projects.state().get("project"),
        mode=lambda: modes.active()["mode"],
        connections=lambda: connection_usage.overview()["connections"],
        usage=connection_usage.usage,
        table_cells=table_cells.listing,
        origin_of=datasets.origins.get,
        kernel_document=workbench.document_of,
        relationships=models.current,
        dashboards=saved_dashboards,
        run_settings=script_runs.settings,
        app_pages=lambda path, text: hooks.app_pages(path, text),
    )
    project_outline.used_tables = BothTables(project_tables.used, project_outline.used_tables)
    project_outline.portability = CardPortability(lambda: connection_usage.overview()["connections"])

    # The system's own file dialog on the user's click (server/dialog_runner.py), and the page's own picker's
    # quick places and recent folders per kind of pick (dialogs.json: paths only).
    def picker_places() -> list[dict[str, str]]:
        found = folder_places()
        for name, kind, folder in (
            ("Projects", "projects", project_explorer.folder()),
            ("Library", "library", str(library_folder.root)),
        ):
            if is_folder(folder):
                found.append({"name": name, "path": folder, "kind": kind})
        return found

    file_dialogs = FileDialogs(
        dialog_runner.DialogRunner(),
        JsonFile(state_dir / "dialogs.json" if audit_log else None),
        picker_places,
        is_folder,
    )

    # The server's life follows the app's windows (services/lifecycle.py): before it stops, the open
    # project's unsaved changes are saved as Autosave does; with Autosave off, the stop waits.
    async def before_stop() -> str:
        current = sab_projects.current
        if current is None or not sab_projects.dirty():
            return ""
        if not current.autosave:
            return "the open project has unsaved changes and Autosave is off"
        try:
            await sab_projects.save({}, "autosave")
        except Exception as error:
            return f"the open project could not be saved: {error}"
        return ""

    lifecycle = Lifecycle(
        windows=live.windows,
        busy=lambda: ["a VS Code window"] if live.openers() else [],
        before_stop=before_stop,
        stop=on_shutdown,
        grace=settings.life_grace_seconds,
        idle=settings.life_idle_seconds,
        start_grace=settings.life_start_grace_seconds,
    )

    grid_service = GridService(ws, datasets.origins.get)
    analysis = Analysis(ws, verifier)
    key_finder = KeyFinder(ws)
    tie_out = TieOut(compares)

    # Export as one Python script: the document's cells, its connections' own code, ruff's check.
    script_exports = ScriptExports(
        ws,
        blade_store,
        read_document=documents.read,
        write_document=documents.write,
        arrange=table_cells.arrange,
        lint=script_lint,
        folder_of=lambda path: str(Path(path).expanduser().parent),
        join=lambda folder, name: str(Path(folder) / name),
        inline=apis.inline,  # an API_<name>.py the document imports travels inside the export
    )
    # A local sandbox API exported for its framework target: the real connections' own code.
    api_export = ApiExport(
        ws,
        sandbox.folder,
        lambda folder: LocalApiFiles.read(str(Path(folder) / local_api_rules.FILE)),
        lambda: Path(api_runtime.__file__).read_text(encoding="utf-8"),
        script_exports,
        ExportFolder(sandbox.copy_now),
        project_scope.edited_in,
        approvals,
        adapter_text=lambda: Path(sab_adapter.__file__).read_text(encoding="utf-8"),
    )
    for extension in on_extensions:
        for raw in getattr(extension, "API_TARGETS", ()) or ():
            api_export.registry.add(api_target_rules.from_extension(raw, str(getattr(extension, "ID", ""))))
    local_api.target_ids = api_export.registry.ids
    local_api.targets = lambda: [{"id": t.id, "label": t.label} for t in api_export.registry.targets.values()]
    local_api.catalog = catalogs

    def publish_api(values: dict[str, str]) -> None:
        for name in ("SAB_API_URL", "SAB_API_KEY", "SAB_API_BASE"):
            if name in values:
                os.environ[name] = values[name]
            else:
                os.environ.pop(name, None)

    local_api.publish = publish_api
    intellisense.sandbox_clients = sandbox.mock_names
    intellisense.sandbox_tables = sandbox.table_columns
    intellisense.sandbox_mocks = sandbox.mock_dialects

    return Services(
        settings=settings,
        ws=ws,
        datasets=datasets,
        file_watch=file_watch,
        code_files=code_files,
        grids=grid_service,
        profiles=Profiles(ws),
        analysis=analysis,
        analyze=Analyze(ws, grid_service, datasets, analysis, tie_out, key_finder, cards, blades),
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
        found_connections=found_connections,
        connection_usage=connection_usage,
        connection_slots=slots,
        apis=apis,
        structures=structures,
        api_explorer=api_explorer,
        catalog_loading=catalog_loading,
        vault_names_at_start=vault_names_at_start,
        connection_tables=connection_tables,
        folders=Folders(
            folder_listing,
            lambda where: ensure_own_folder(where, settings.workbench_dir),
            places=file_dialogs.places,
            make_folder=make_folder,
        ),
        file_dialogs=file_dialogs,
        workbench=workbench,
        models=models,
        project_tables=project_tables,
        finder=Finder(ws, models),
        library=library,
        library_setup=library_setup,
        team=team,
        sharing=sharing,
        sandbox=sandbox,
        local_api=local_api,
        api_export=api_export,
        shared_catalog=shared_catalog,
        app_registrations=app_registrations,
        keys=key_finder,
        compares=compares,
        tie_out=tie_out,
        snapshots=Snapshots(ws),
        workbench_window=workbench_window,
        intellisense=intellisense,
        script_ide=script_ide,
        debugger=Debugger(
            ws,
            lambda kernel: cast(
                "DebugKernel | None", workbench.kernel_or_none(kernel)
            ),  # server/kernels.py's
            workbench.kernel_for,
            workbench.document_of,
        ),
        table_cells=table_cells,
        modes=modes,
        switched_on=on_extensions,
        hooks=hooks,
        data_export=data_export,
        documents=documents,
        project_files=project_files,
        export_writer=export_writer,
        process_event=process_event,
        session_log=session_log,
        variables=variables,
        explorer=explorer,
        connection_swap=connection_swap,
        navigation=Navigation(ws, JsonFile(state_dir / "rail.json" if audit_log else None)),
        script_runs=script_runs,
        connection_colours=connection_colours,
        beta=beta,
        updates=updates,
        extensions=extensions,
        lifecycle=lifecycle,
        desktop=Desktop(SystemShell(info_file_path()), ws.audit, qt_version()),
        claude=claude,
        context_md=context_md,
        lineage=Lineage(
            ws,
            hooks,
            datasets.origins,
            documents.read,
            project_files,
            workbench.lineage_values,
            kernel_for=workbench.kernel_for,
        ),
        projects=projects,
        sab_projects=sab_projects,
        project_explorer=project_explorer,
        project_scope=project_scope,
        project_outline=project_outline,
        script_exports=script_exports,
        live=live,
        workers=workers,
    )
