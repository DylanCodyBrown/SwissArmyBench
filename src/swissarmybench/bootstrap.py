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
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, cast

import duckdb

from swissarmybench import __version__
from swissarmybench import extensions as extension_modules
from swissarmybench.adapters import adapter, api_adapter, blade_run
from swissarmybench.adapters import code_files as code_file_disk
from swissarmybench.adapters import datasets as table_reader
from swissarmybench.adapters import environment as environment_files
from swissarmybench.adapters import export as export_writer
from swissarmybench.adapters.apis import ApiFiles, ApiLibrary, SpecSource
from swissarmybench.adapters.app_registrations import MicrosoftProbe, RegistrationFiles
from swissarmybench.adapters.beta_log import BetaFiles, BetaSwitch
from swissarmybench.adapters.beta_log import listen as listen_for_crashes
from swissarmybench.adapters.blades import BladeStore
from swissarmybench.adapters.call_stats import StatsFiles
from swissarmybench.adapters.catalogs import CatalogStore
from swissarmybench.adapters.changes import ChangeFiles
from swissarmybench.adapters.claude import ClaudeFiles
from swissarmybench.adapters.codegen import Verifier
from swissarmybench.adapters.connection_colours import ColoursFile
from swissarmybench.adapters.database import PriorityWorkers, duckdb_grammar, grammar_later, open_database
from swissarmybench.adapters.datasets import DatasetStore, file_stamp
from swissarmybench.adapters.extensions import FolderExtensions
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
from swissarmybench.adapters.sandbox import gitignore as sandbox_gitignore
from swissarmybench.adapters.scaffold import ScaffoldFiles
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
    publish_api,
)
from swissarmybench.adapters.vault_names import VaultNameFiles
from swissarmybench.adapters.views import ViewEngine
from swissarmybench.adapters.workbench import Documents
from swissarmybench.client import kernel_intel
from swissarmybench.domain import api_patterns as api_pattern_rules
from swissarmybench.domain import api_targets as api_target_rules
from swissarmybench.domain import blade_tables, python_connections
from swissarmybench.domain import connection_slots as slot_rules
from swissarmybench.domain import connection_tables as connection_table_rules
from swissarmybench.domain import connections as connection_rules
from swissarmybench.domain import context_md as context_rules
from swissarmybench.domain import extensions as extension_rules
from swissarmybench.domain import library as library_rules
from swissarmybench.domain import library_setup as setup_rules
from swissarmybench.domain import local_api as local_api_rules
from swissarmybench.domain import projects as project_rules
from swissarmybench.domain import sandbox as sandbox_rules
from swissarmybench.domain import scaffold as scaffold_rules
from swissarmybench.domain import variables as variable_rules
from swissarmybench.domain.blades import Blade, env_settings
from swissarmybench.domain.codegen import variable_name
from swissarmybench.domain.connection_swap import Place
from swissarmybench.domain.context_md import CatalogTable
from swissarmybench.domain.grids import GridRegistry
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
from swissarmybench.server.environments import ProjectLibraries, make_venv
from swissarmybench.server.kernels import Launcher
from swissarmybench.server.script_check import lint as script_lint
from swissarmybench.server.text_process import run_text
from swissarmybench.server.tunnels import DevTunnelProgram
from swissarmybench.server.updater import Helper as UpdateHelper
from swissarmybench.services import explorer as explorer_providers
from swissarmybench.services.actions import Actions
from swissarmybench.services.agent import AgentService, Approvals, ExportTickets
from swissarmybench.services.analysis import Analysis
from swissarmybench.services.analyze import Analyze
from swissarmybench.services.api_explorer import Explorer as ApiExplorer
from swissarmybench.services.api_export import ApiExport
from swissarmybench.services.apis import Apis
from swissarmybench.services.app_registrations import AppRegistrations
from swissarmybench.services.beta_log import BetaLog
from swissarmybench.services.blades import BladeService
from swissarmybench.services.call_stats import CallStats
from swissarmybench.services.catalog_loading import CatalogLoading
from swissarmybench.services.catalogs import CatalogService
from swissarmybench.services.changes import ChangeLog
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
from swissarmybench.services.environment import Environment, sources_from
from swissarmybench.services.explorer import BrowseSources, Explorer, OpenTable
from swissarmybench.services.export import Exports
from swissarmybench.services.extensions import Extensions
from swissarmybench.services.file_dialogs import FileDialogs
from swissarmybench.services.file_watch import FileWatch
from swissarmybench.services.folders import Folders
from swissarmybench.services.found_connections import FoundConnections
from swissarmybench.services.grids import GridService
from swissarmybench.services.grids import view_rows as grid_view_rows
from swissarmybench.services.hooks import Hooks
from swissarmybench.services.inbox import Inbox
from swissarmybench.services.intellisense import Intellisense
from swissarmybench.services.library import Library
from swissarmybench.services.library_setup import LibrarySetup, SharedProjects
from swissarmybench.services.lifecycle import Lifecycle
from swissarmybench.services.lineage import Lineage
from swissarmybench.services.local_api import LocalApi
from swissarmybench.services.modes import Modes
from swissarmybench.services.navigation import Navigation
from swissarmybench.services.processes import ProcessRegistry, Sessions
from swissarmybench.services.profile import Profiles
from swissarmybench.services.project_explorer import ProjectExplorer
from swissarmybench.services.project_outline import BothTables, CardPortability, ProjectOutline
from swissarmybench.services.project_python import ProjectPython
from swissarmybench.services.project_scope import ProjectScope, ProjectUse, UseSources
from swissarmybench.services.projects import Projects
from swissarmybench.services.regression import Regression
from swissarmybench.services.relationship_scope import ProjectTables
from swissarmybench.services.relationships import Compares, Finder, KeyFinder, Models
from swissarmybench.services.sab_projects import SabProjects
from swissarmybench.services.sandbox import Sandbox, SandboxAlias, SourcesFrom
from swissarmybench.services.scaffold import Scaffold
from swissarmybench.services.scaffold import Sources as ScaffoldSources
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
from swissarmybench.services.updates import Updates, what_is_open
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
    call_stats: CallStats
    changes: ChangeLog
    apis: Apis
    structures: Structures
    api_explorer: ApiExplorer
    actions: Actions
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
    environment: Environment
    project_python: ProjectPython
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
    scaffold: Scaffold
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
    state_file: Callable[[str], Path | None],
) -> Workspace:
    """The workspace: the ports every use case shares."""
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
        audit=Heard(AuditLog(state_file("audit.log")), session_log),
        grammar=grammar_later(),  # read from DuckDB on the first query, not at start
        interrupted=duckdb.InterruptException,
        engine_error=duckdb.Error,
    )


def _beta_log(
    ws: Workspace,
    settings: Settings,
    store: DatasetStore,
    token: str,
    state_file: Callable[[str], Path | None],
) -> BetaLog:
    """The beta log: errors, slow requests, processes, page errors and notes, redacted (written only where
    the audit log is; beta mode on or off is beta.json, SWISSARMYBENCH_BETA wins)."""
    return BetaLog(
        ws,
        BetaFiles(state_file("logs"), settings.beta_log_bytes, settings.beta_log_days),
        BetaSwitch(state_file("beta.json")),
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


# ----- the app's own life: extensions, the Team box, sharing, updates (bootstrap's order) -----


def _extensions(
    ws: Workspace, live: LiveUpdates, approvals: Approvals, state_dir: Path,
    state_file: Callable[[str], Path | None],
    on_extensions: list[Any], on_shutdown: Callable[[], None] | None, install_packages: Any,
) -> tuple[UpdateHelper, Extensions]:  # fmt: skip
    """Extensions (the Extensions page): the installed ones found once, at start; Install and Remove hand
    over to the update's helper, and each update keeps the installed ones (`--with`). The library's folder
    extensions are read live (FolderExtensions): their packages go into the app's own Python (the blades'
    install), their folders to the system's trash on Remove, shown in its file manager on Show its folder."""
    update_helper = UpdateHelper(info_file_path(), state_dir / "update_failed.json")
    extensions = Extensions(
        current=__version__,
        found=discover_extensions(os.environ),
        helper=update_helper,
        approvals=approvals,
        audit=ws.audit,
        live=live,
        stop=on_shutdown or (lambda: None),
        record=JsonFile(state_file("extensions.json")),
        folders=FolderExtensions(file_manager.trash, file_manager.show),
        install_packages=install_packages,
        panels={
            str(getattr(m, "ID", "")).lower(): str(m.PANEL)
            for m in on_extensions
            if isinstance(getattr(m, "PANEL", None), str) and str(m.PANEL).startswith("/")
        },
    )
    update_helper.kept = extensions.kept_wheels
    return update_helper, extensions


def _team(
    ws: Workspace, hooks: Hooks, library: Library, project_explorer: ProjectExplorer, library_setup: Any,
    file_manager: Any, approvals: Approvals, extensions: Extensions, state_dir: Path,
    state_file: Callable[[str], Path | None],
) -> Team:  # fmt: skip
    """Settings' Team box: one GitHub repository for the team library and its projects/ (team.json: the
    team joined, the folders before it, a step kept over Install's restart). The GitHub work is an
    extension's."""
    syncing = next((e for e in extension_rules.CATALOG if "team" in e.provides), None)
    return Team(
        ws,
        hooks,
        library,
        project_explorer,
        library_setup,
        JsonFile(state_file("team.json")),
        TeamFiles(file_manager.show),
        str(state_dir),
        approvals,
        lambda: {
            "id": syncing.id if syncing else "",
            "name": syncing.name if syncing else "",
            "installable": extensions.state()["installable"],
        },
    )


def _sharing(ws: Workspace, hooks: Hooks, approvals: Approvals, state_dir: Path, port: int) -> Sharing:
    """Share a running app with your organization (Microsoft Dev Tunnels; the third way data leaves this
    computer, on the user's click): devtunnel in the state folder's devtunnel/, got on the first share."""
    sharing = Sharing(
        ws,
        DevTunnelProgram(TunnelFiles(state_dir / "devtunnel")),
        lambda: hooks.share_targets,
        approvals,
        port,
    )
    hooks.sharing = sharing
    return sharing


def _updates(
    ws: Workspace, live: LiveUpdates, settings: Settings, update_helper: UpdateHelper, extensions: Extensions,
    approvals: Approvals, open_work: Any, failure_note: Path | None,
    state_file: Callable[[str], Path | None],
    on_shutdown: Callable[[], None] | None,
) -> Updates:  # fmt: skip
    """The update check (the one request that leaves the computer, the owner's call) and Update to X."""
    return Updates(
        current=__version__,
        feeds=settings.update_feeds,
        feed=HttpFeed(),
        switch=UpdateSwitchFile(state_file("update.json")),
        helper=update_helper,
        open_work=open_work,
        approvals=approvals,
        audit=ws.audit,
        live=live,
        stop=on_shutdown or (lambda: None),
        failed=take_failure_note(failure_note),
        changing=extensions.changing,
    )


# ----- what context.md reads of the connections -----


async def _catalog_of(catalogs: Any, name: str) -> Any:
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


def _inside(path: str | None, folder: str) -> bool:
    """Whether a path is inside a project folder, by their real paths (what the project uses)."""
    if not path or not folder:
        return False
    root = os.path.realpath(folder).replace("\\", "/").rstrip("/") + "/"
    return os.path.realpath(path).replace("\\", "/").startswith(root)


def _explorer(
    ws: Workspace,
    datasets: DatasetService,
    connections: ConnectionService,
    connection_tables: Any,
    catalogs: Any,
    catalog_loading: Any,
    shared_catalog: Any,
    variables: Any,
    blades: Any,
    structures: Any,
) -> Explorer:
    """The Data Explorer: one search over the connections and their catalogs, the open tables, the
    variables and the blades, Structures' documents and paths, APIs' web calls that return a table.
    The Data page browses the same sources: each connection's tree (never loaded by a look: Load does)."""
    store = ws.store
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
    return explorer


def _app_registrations(
    ws: Workspace,
    connections: ConnectionService,
    blade_store: BladeStore,
    library_folder: LibraryFolder,
    variables: Any,
    tables_of: Callable[[str], Any],
) -> AppRegistrations:
    """The library's app registrations, each one's users being the connections that read its variables; a
    connection's tables from its loaded catalog (Azure SQL's SELECT TOP 0 on them)."""

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
        tables_of=tables_of,
    )
    return app_registrations


def _variables_once(state_dir: Path, library: Any, variables: Any) -> None:
    """Once (12.7: a password field holds ${NAME}): each connection's own saved password becomes a keyring
    variable, its connection's file backed up first; then what saved text now reads a variable (once)."""
    # Once (12.7: a password field holds ${NAME}): each connection's own saved password becomes a keyring
    # variable, its connection's file backed up first; then what saved text now reads a variable (once).
    today = datetime.now(UTC).date().isoformat()
    passwords_moved = JsonFile(state_dir / "variables_moved.json")  # once: the first start with 12.7
    if passwords_moved.read() is None:
        library.notice(
            "computer",
            variables.migrate_passwords(backup_copies(state_dir / "backup" / f"before-variables-{today}")),
        )
        passwords_moved.write({"moved": today})
    refs_seen = JsonFile(state_dir / "variable_refs.json")
    holding = variables.holding() if refs_seen.read() is None else []
    if holding:  # said once; nothing found writes nothing
        library.notice("computer", variable_rules.holding_words(holding))
        refs_seen.write({"listed": today})


class Built:
    """What bootstrap() has built so far (adapter phase 5, 2026-11-22: the smallest typed record that works).
    Each area's part below reads what it needs from it and adds what it makes, in bootstrap's order; a
    closure reads a later one when it runs (a service made after it: the sandbox, the variables, the
    structures), as the closures inside bootstrap() did. The doors get Services, made from it at the end."""

    # ----- given -----
    port: int
    token: str
    settings: Settings
    on_shutdown: Callable[[], None] | None
    # Whether this server writes its state files at all (create_app's audit_log=False: the tests' servers
    # write none): read through state_file() and library_files(), never as a flag of its own.
    persist: bool
    state_dir: Path
    export_dir: Path
    on_extensions: list[Any]
    # ----- the adapters, the workspace, the beta log -----
    connection: Any
    workers: PriorityWorkers
    store: DatasetStore
    live: LiveUpdates
    library_folder: LibraryFolder
    kept_vault_names: KeptVaultNames
    blade_store: BladeStore
    verifier: Verifier
    session_log: SessionLog
    ws: Workspace
    beta: BetaLog
    # ----- a connection's runs (each through its slots) -----
    process_event: Callable[..., None]
    run_blade: Callable[..., Any]
    stream_blade: Callable[..., Any]
    vault_environment: Callable[[], Any]
    given_out: Callable[[dict[str, Any]], None]
    vault_values: Callable[..., Any]
    secrets_of: Callable[[str], list[str] | None]
    files_of: Callable[[str], list[str]]
    # ----- the services, in the order they are made -----
    processes: ProcessRegistry
    tickets: ExportTickets
    approvals: Approvals
    slots: ConnectionSlots
    call_stats: CallStats
    changes: ChangeLog
    datasets: DatasetService
    file_watch: FileWatch
    catalogs: CatalogService
    blades: BladeService
    catalog_loading: CatalogLoading
    vault_names_at_start: VaultNamesAtStart
    compares: Compares
    models: Models
    documents: Documents
    script_runs: ScriptRuns
    table_cells: TableCells
    project_files: ProjectFiles
    hooks: Hooks
    data_export: DataExport
    workbench: Workbench
    connection_colours: ConnectionColours
    connections: ConnectionService
    connection_usage: ConnectionUsage
    api_library: ApiLibrary
    apis: Apis
    workbench_window: WorkbenchWindow
    dashboards: DashboardFiles
    cards: Cards
    projects: Projects
    archive: SabArchive
    library: Library
    recent_projects: RecentProjects
    sab_projects: SabProjects
    project_explorer: ProjectExplorer
    structures: Structures
    api_explorer: ApiExplorer
    connection_tables: ConnectionTablesService
    connection_swap: ConnectionSwap
    project_use: ProjectUse
    project_documents: Callable[[], tuple[set[str], list[tuple[str, str]]] | None]
    project_tables: ProjectTables
    connections_here: Callable[[], list[Here]]
    shared_catalog: SharedCatalog
    code_files: CodeFiles
    project_scope: ProjectScope
    variables: Variables
    found_connections: FoundConnections
    app_registrations: AppRegistrations
    shared_projects: SharedProjects
    library_setup: LibrarySetup
    explorer: Explorer
    sandbox: Sandbox
    sandbox_alias: SandboxAlias
    local_api: LocalApi
    sessions: Sessions
    environment: Environment
    project_python: ProjectPython
    actions: Actions
    update_helper: UpdateHelper
    extensions: Extensions
    team: Team
    sharing: Sharing
    updates: Updates
    claude_files: ClaudeFiles
    agent: AgentService
    intellisense: Intellisense
    script_ide: ScriptIde
    context_md: ContextMd
    claude: Claude
    modes: Modes
    project_outline: ProjectOutline
    file_dialogs: FileDialogs
    lifecycle: Lifecycle
    grid_service: GridService
    analysis: Analysis
    key_finder: KeyFinder
    tie_out: TieOut
    script_exports: ScriptExports
    api_export: ApiExport
    scaffold: Scaffold

    def state_file(self, name: str) -> Path | None:
        """A state file's path in the state folder, or None when this server writes no state files."""
        return self.state_dir / name if self.persist else None

    def library_files(self) -> Callable[[], Path] | None:
        """The library folder's root as its stores read it, or None when this server writes no state files."""
        library_folder = self.library_folder
        return (lambda: library_folder.root) if self.persist else None

    def has(self, name: str) -> bool:
        """Whether that part is built yet (a closure made before it asks, as the ready lists did)."""
        return name in vars(self)


def bootstrap(
    port: int,
    token: str,
    settings: Settings | None = None,
    on_shutdown: Callable[[], None] | None = None,
    audit_log: bool = True,
) -> Services:
    """Build everything for a server listening on 127.0.0.1:`port` that accepts `token`: the adapters, the
    workspace, then each area's services, in this order (each part reads what it needs from what is built)."""
    b = Built()
    # audit_log=False (the tests' servers): no state file is written at all, the audit log among them.
    b.port, b.token, b.on_shutdown, b.persist = port, token, on_shutdown, audit_log
    b.settings = settings or Settings()
    b.state_dir, b.export_dir = b.settings.state_dir, b.settings.export_dir
    # The library's folder extensions (its extensions/<id>/) are this server's library's: pointed at it first.
    extension_modules.use_library(LibraryFolder(b.settings.library_dir, b.state_file("library.json")).root)
    b.on_extensions = extension_modules.enabled()
    for part in (
        _adapters,
        _connection_runs,
        _workspace_and_beta,
        _data,
        _models_and_cells,
        _workbench_part,
        _connections,
        _projects,
        _structures_and_apis,
        _shared_catalog_part,
        _variables_part,
        _setup_and_explorer,
        _sandbox_part,
        _app_life,
        _editors_and_claude,
        _outline_dialogs_and_life,
        _exports,
    ):
        part(b)
    _check_wired(b)
    return _services(b)


# What a part sets on a service once a later one is built (a true cycle, or a service made after it): each
# checked at the end of bootstrap(), so a part moved before what it needs fails at start, not on a click.
LATE_BOUND = (
    "update_helper.kept",
    "hooks.sharing",
    "ws.audit.changes",
    "datasets.changed_on_disk",
    "datasets.not_now",
    "datasets.origins.document_of",
    "datasets.connection_sql",
    "datasets.variables",
    "blades.open_table",
    "blades.lint",
    "slots.kernel_caller",
    "slots.interrupt_kernel",
    "sab_projects.shared_folder",
    "structures.rerun",
    "structures.hash_of",
    "structures.touched",
    "structures.variables",
    "api_explorer.variables",
    "library.catalog_info",
    "project_tables.shared",
    "kept_vault_names.vaults",
    "kept_vault_names.defined",
    "connections.variable_check",
    "project_python.end_session",
    "project_python.session_kernel",
    "project_python.forget_environment",
    "workbench.project",
    "workbench.moved_environment",
    "connection_usage.extra_cards",
    "connection_colours.fixed",
    "local_api.learned",
    "local_api.target_ids",
    "local_api.targets",
    "project_outline.used_tables",
    "project_outline.portability",
)


def _check_wired(b: Any) -> None:
    """Every part built what it names (each Built field set), and every late-bound attribute set by its part:
    not None, and not the stand-in a service's own constructor gave it (a lambda made in its __init__)."""
    problems = [f"{name} was not built" for name in Built.__annotations__ if name not in vars(b)]
    for path in LATE_BOUND:
        owner: Any = b
        try:
            for part in path.split("."):
                owner = getattr(owner, part)
        except AttributeError:
            problems.append(f"{path} is not there")
            continue
        if owner is None or "__init__.<locals>" in str(getattr(owner, "__qualname__", "")):
            problems.append(f"{path} was not set")
    if problems:
        raise RuntimeError("bootstrap's parts are out of order: " + "; ".join(problems) + ".")


# ----- the adapters: DuckDB, the dataset store, the live updates, the library's files -----


def _adapters(b: Built) -> None:
    settings = b.settings
    b.connection = open_database(settings.duckdb_memory_limit)
    b.workers = PriorityWorkers(settings.worker_threads)
    b.store = DatasetStore(
        b.connection, settings.max_dataset_bytes, settings.max_total_bytes, settings.max_datasets
    )
    b.live = LiveUpdates()
    # The library (Plans/library.plan.md): this computer's connections, APIs, vaults, blades, relationship
    # sets, variables and colours, in one folder made to be a Git repository, whatever project is open;
    # Settings points it elsewhere (library.json: the path only). README.md and .gitignore made on first use.
    b.library_folder = LibraryFolder(settings.library_dir, b.state_file("library.json"))
    library_folder = b.library_folder
    # A key vault's secret names as last read here (the library's local/vault-names/: names only, never a
    # value): a vault that loads every secret gives its variables from the first second after a start.
    b.kept_vault_names = KeptVaultNames(
        VaultNameFiles(b.library_files(), library_folder.ensure),
        lambda: datetime.now(UTC).isoformat(timespec="seconds"),
    )
    b.blade_store = _blade_store(settings, library_folder, b.on_extensions)
    b.verifier = Verifier(settings.duckdb_memory_limit)


# ----- a connection's runs: a blade's child process, through the connection's slots, counted -----


def _connection_runs(b: Built) -> None:
    settings, blade_store = b.settings, b.blade_store

    def process_event(
        kind: str, event: str, code: int | None, seconds: float | None, reason: str = ""
    ) -> None:
        b.beta.process(kind, event, code, seconds, reason)

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
            answer = await b.slots.run_blade(blade.name, blade.kind, blade.dialect, mode, extra, work)
        except Exception as error:
            b.connection_usage.record(blade.name, mode, ok=False, error=str(error))
            raise
        about = answer.get("about") if isinstance(answer, dict) else None
        b.connection_usage.record(blade.name, mode, ok=True, about=about if isinstance(about, dict) else None)
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
        b.connection_usage.record(
            blade.name, "test", ok=bool(answer.get("ok")), error=str(answer.get("failed") or "")
        )
        return answer

    given_out = partial(_given_out, b.kept_vault_names, blade_store)

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
                await b.blades.keep_names(str(vault), connection_rules.vault_names(listed))
        return values, [str(p) for p in answer.get("problems") or []]

    b.process_event, b.run_blade, b.stream_blade = process_event, run_blade, stream_blade
    b.given_out, b.vault_environment = given_out, vault_environment
    b.vault_values = partial(_vault_values, blade_store, settings.vault_timeout_seconds)
    b.secrets_of = partial(_secrets_of, blade_store)
    b.files_of = partial(_files_of, blade_store)


def _workspace_and_beta(b: Built) -> None:
    """The workspace (the ports every use case shares) and the beta log (errors, slow requests, processes,
    page errors and notes, redacted; written only where the audit log is; beta mode on or off is beta.json,
    SWISSARMYBENCH_BETA wins; read each time: the Variables page's values join the environment as added)."""
    b.session_log = SessionLog(b.live, JsonFile(b.state_file("follow.json")))
    b.ws = _workspace(
        b.settings, b.port, b.token, b.store, b.connection, b.live, b.workers, b.session_log, b.state_file
    )
    b.beta = _beta_log(b.ws, b.settings, b.store, b.token, b.state_file)


# ----- the data: the open tables, the catalogs, the blades -----


def _data(b: Built) -> None:
    ws, settings, state_dir, blade_store = b.ws, b.settings, b.state_dir, b.blade_store
    b.processes = ProcessRegistry()  # the Python sessions offering tables to the Open list
    b.tickets = ExportTickets()  # the agent exports the user approved, not yet written
    # The questions for the user that the agent's requests wait on (the page's approval prompt): one
    # for every use case that writes the user's rows to disk for the agent.
    b.approvals = Approvals(b.live)
    # How many queries run at once on each connection, the agent's share and the line (the owner,
    # 2026-11-21): the one gate run_blade passes through; a kernel's slot is leased by its routes.

    # Every call's statistics (Plans/stats.plan.md): the slots' finished calls, the adapter's and the API
    # adapter's facts in this process; the running figures in the open project's .sab/stats.json. No value.
    def project() -> str | None:
        return b.sab_projects.current.folder if b.has("sab_projects") and b.sab_projects.current else None

    def stamp() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds")

    b.call_stats = CallStats(StatsFiles(), project, stamp)
    # The change log (Plans/changes.plan.md): each change a service raises on its audit entry, heard with
    # the Session page's and written as it happens to the open project's .sab/changes.jsonl.
    b.changes = ChangeLog(ChangeFiles(), project, stamp)
    if isinstance(ws.audit, Heard):
        ws.audit.changes = b.changes
    b.slots = ConnectionSlots(
        b.live,
        ws.audit,
        limits_of=lambda name: slot_rules.limits_of_header(blade_store.get(name).queries),
        save_limits=lambda name, header: blade_store.set_header(name, {"queries": header}).name,
        ask=b.approvals.ask,
        on_finished=b.call_stats.finished,
    )
    adapter.observe(b.call_stats.adapter)
    api_adapter.observe(b.call_stats.api_observed)
    b.datasets = datasets = DatasetService(
        ws,
        table_reader,
        b.processes,
        own_file=lambda path: is_own_file(path, state_dir, b.export_dir),
        on_shutdown=b.on_shutdown or (lambda: None),
    )
    # A table read from a file is watched: changed on disk, the page says so (Reload, Not now).
    b.file_watch = FileWatch(ws, datasets.origins.get, file_stamp, settings.file_watch_seconds)
    datasets.changed_on_disk = b.file_watch.changed
    datasets.not_now = b.file_watch.not_now
    b.catalogs = CatalogService(
        ws, CatalogStore(b.connection, settings.max_catalogs, settings.max_catalog_rows), table_reader
    )
    b.blades = blades = BladeService(
        ws,
        blade_store,
        b.catalogs,
        TEMPLATES,
        blade_run.needed,
        b.run_blade,
        blade_runner.install_packages,
        python=sys.executable,
        environ=os.environ,
        reveal=lambda path: file_manager.reveal(path),  # Show its file (looked up when clicked)
        kept_names=b.kept_vault_names,
        stream_blade=b.stream_blade,
    )
    # The blade IDE's Open as grid: a run's table in a tab of its own.
    blades.open_table = lambda name, table, who: datasets.store_table(
        datasets.free_name(name), table, "blade", True, who
    )
    b.catalog_loading = CatalogLoading(
        ws, blades, b.catalogs, settings.auto_load_catalogs, settings.catalogs_at_once, b.live.windows
    )
    # A vault that loads every secret: its names read again once the first window is open (kept meanwhile).
    b.vault_names_at_start = VaultNamesAtStart(
        blades,
        b.kept_vault_names,
        b.live.broadcast,
        settings.auto_read_vaults,
        settings.catalogs_at_once,
        b.live.windows,
    )


def _models_and_cells(b: Built) -> None:
    """Relationships, a script's run settings, every table's read-only cell, what extensions hand back."""
    ws, state_dir, library_folder, blade_store = b.ws, b.state_dir, b.library_folder, b.blade_store
    # Relationship sets come from the person's own folder and the shared folders, which are the blade
    # folders: one team folder carries blades and sets alike.
    b.compares = Compares(ws)
    b.models = Models(
        ws,
        ModelFiles(
            state_dir,
            shared=lambda: [f["path"] for f in blade_store.folders() if f["exists"]],
            library=lambda: library_folder.root,
            made=library_folder.ensure,
        ),
        b.approvals,
    )
    b.datasets.renamed.append(b.models.rename_table)
    b.documents = Documents(state_dir / "recent.json", b.settings.workbench_dir)
    b.script_runs = ScriptRuns(
        ws,
        JsonFile(b.state_file("run_settings.json")),
        b.documents,
        secrets_of=b.secrets_of,
        files_of=b.files_of,
    )
    b.table_cells = TableCells(
        ws,
        b.datasets.origins,
        table_reader.query_to_arrow_stream,  # type: ignore[arg-type]
        table_reader.planned_arrow_stream,  # type: ignore[arg-type]
    )
    b.project_files = ProjectFiles()
    # What the extensions that are on hand back once they are built (services/hooks.py): the documents the
    # Workbench windows hold, what stops with a kernel or a window, a canvas, an app's file.
    b.hooks = hooks = Hooks()
    b.data_export = DataExport(
        b.project_files,
        b.table_cells.arrange,
        lambda path: hooks.held(path),
        lambda folder: b.project_scope.edited_in(folder),  # data.py edited by hand: kept (Scripts IDE)
    )


def _workbench_part(b: Built) -> None:
    """The Workbench and its kernels: each kernel's queries through its connection's slots."""
    b.workbench = workbench = Workbench(
        b.ws,
        b.documents,
        Launcher(report=lambda *e: b.process_event("kernel", *e)),
        os.environ,
        now=time.time,
        folder_of=lambda path: str(Path(path).expanduser().parent),
        secret_names=b.blades.environment_names,
        vault_environment=b.vault_environment,
        hooks=b.hooks,
    )

    def kernel_caller(kernel: str) -> Caller:
        role, words = workbench.runner_of(kernel)
        document = workbench.document_of(kernel)  # Open its source: the document in the Workbench
        source = {"document": document} if document else {}
        return Caller(role, "The agent" if role == "agent" else words, kernel=kernel, source=source)

    async def kernel_ended(kernel: str) -> None:
        b.slots.kernel_stopped(kernel)  # its slots go back at once

    b.datasets.origins.document_of = workbench.document_of  # a table a kernel sends: the document it ran for
    b.slots.kernel_caller = kernel_caller
    b.slots.interrupt_kernel = workbench.interrupt
    workbench.set_kernel_stopped(kernel_ended)


# ----- connections, APIs, cards and projects -----


def _connections(b: Built) -> None:
    ws, blades, library_folder, state_dir = b.ws, b.blades, b.library_folder, b.state_dir
    # Each connection's colour: the library's colours.toml, the same in every project; never one of the
    # rail's (the kind colours, the accent).
    b.connection_colours = ConnectionColours(
        ws,
        blades,
        ColoursFile(
            (lambda: library_folder.root / library_rules.COLOURS_FILE) if b.persist else None,
            library_folder.ensure,
        ),
    )
    b.connections = connections = ConnectionService(
        blades,
        TEMPLATES,
        on_saved=b.catalog_loading.saved,
        catalog_state=b.catalog_loading.state,
        tables=ConnectionTables(b.datasets),
        models=b.models,
        catalogs=b.catalogs,
        colours=b.connection_colours,
        # sab.write for the agent (connections_write): its Allow, and an open table's grid view as rows.
        approvals=b.approvals,
        open_view=b.table_cells.view,
    )
    # The Connections page: each connection's references, configuration and calls this session.
    b.connection_usage = ConnectionUsage(
        ws,
        blades,
        connections,
        documents=lambda: usage_documents(b.documents, b.hooks, b.sab_projects, b.project_files),
        read=b.documents.read,
        origin_of=b.datasets.origins.get,
        environ=os.environ,
        now=time.time,
        figures_of=lambda name: b.call_stats.figures_of("connection", [name]).get(name),
    )
    # Add API: the library's apis/<name>/: API_<name>.py, its API blade and web call blades.
    b.api_library = ApiLibrary(lambda: library_folder.root / library_rules.APIS, library_folder.ensure)
    b.apis = Apis(
        ws,
        ApiFiles(),
        SpecSource(),
        connections,
        b.api_library,
        blades,
        now=lambda: datetime.now(UTC).isoformat(timespec="seconds"),
    )
    b.workbench_window = WorkbenchWindow(ws)
    b.dashboards = DashboardFiles(state_dir / "dashboards")
    b.cards = Cards(ws, b.dashboards, ThemeFiles(state_dir / "themes"))
    b.projects = Projects(
        ws,
        b.project_files,
        b.table_cells.group_cells,
        export_data=b.data_export.export_data,
        project_app=lambda name: b.hooks.project_app(name),
        remember=lambda path: b.documents.remember(path, time.time()),
        approvals=b.approvals,
        scaffold=_scaffold_of,
    )
    # A project is a folder: its .sab/ state written beside its files.
    b.archive = SabArchive(b.settings.max_project_entries, b.settings.max_project_read_bytes)


async def _use_project(b: Built, folder: str | None) -> None:
    """The open project's saved dashboards (its .sab/visualizations), or this computer's with none open.
    Connections, APIs, vaults, blades and variables are the library's, whatever is open."""
    app = Path(folder) / APP_FOLDER if folder else None
    b.dashboards.folder = app / "visualizations" if app else b.state_dir / "dashboards"
    await b.catalog_loading.rescope()
    await b.variables.rescope()
    await b.live.broadcast({"type": "blades_changed"})
    if b.has("structures"):
        await b.structures.project_changed(folder)  # the closed project's structures go with it
    if b.has("project_python"):
        await b.project_python.project_changed(folder)  # its one Python session, and its own .venv


async def _library_moved(b: Built) -> None:
    """Settings' Library folder changed: every store reads the new folder (the pages told)."""
    live = b.live
    b.blade_store.use(b.library_folder.root)
    await b.catalog_loading.rescope()
    await b.variables.rescope()
    await live.broadcast({"type": "blades_changed"})
    await live.broadcast({"type": "connection_colours_changed"} | b.connection_colours.get())
    if b.has("shared_catalog"):
        b.shared_catalog.load()  # the new folder's catalog/
        await live.broadcast({"type": "catalog_changed", "from": "folder", "changed": 0})
    if b.has("library_setup"):
        b.library_setup.forget()
    counts = b.library_folder.counts()
    said = setup_rules.setup_notice(counts["connections"], counts["vaults"])
    if said:  # a team's meta store, pointed at: what this computer needs is on Settings' checklist
        await live.broadcast({"type": "library_notice", "text": said})


def _projects(b: Built) -> None:
    """The library, a project as a folder, and the Project Explorer (the home page)."""
    ws, settings = b.ws, b.settings
    b.library = library = Library(
        ws, b.library_folder, b.blade_store, b.approvals, partial(_library_moved, b)
    )
    b.recent_projects = RecentProjects(b.state_file("recent_projects.json"))
    b.sab_projects = sab_projects = SabProjects(
        ws,
        b.archive,
        b.recent_projects,
        b.datasets,
        b.connections,
        b.cards,
        b.models,
        b.projects,
        table_reader,
        b.approvals,
        version=__version__,
        now=time.time,
        kernel_document=b.workbench.document_of,
        ask_workbench=lambda command, args: b.workbench_window.ask(command, args, "app"),
        scope=partial(_use_project, b),
        adopt=library.adopt_project,
        autosave_seconds=settings.autosave_seconds,
        # the projects folder New uses
        projects_folder=lambda: (
            b.project_explorer.folder() if b.has("project_explorer") else str(settings.projects_dir)
        ),
    )
    # The Project Explorer (the home page): every project in one place, sortable, the types explained.
    b.project_explorer = ProjectExplorer(
        ws,
        ExplorerFiles(file_manager.show, file_manager.trash),
        ExplorerSettings(b.state_file("projects.json")),
        b.recent_projects,
        sab_projects,
        b.approvals,
        default_folder=str(settings.projects_dir),
        modes=extension_modules.modes,
        streamlit=extension_modules.STREAMLIT_KIND,
        off=lambda: {
            str(e["project_type"]): e
            for e in extension_rules.off_project_types(extension_rules.CATALOG, extension_modules.modes())
        },
    )
    sab_projects.shared_folder = b.project_explorer.shared_folder


def _structures_and_apis(b: Built) -> None:
    """Structures, the APIs page, what a connection's tables are, a table's connection swapped, and the
    tables the open project uses."""
    ws, datasets, documents, hooks, sab_projects = b.ws, b.datasets, b.documents, b.hooks, b.sab_projects
    # Structures: nested data (JSON, YAML, XML, TOML) as documents; the project's own in structures/.
    b.structures = structures = Structures(
        ws,
        StructureFiles(),
        StructureCodecs(),
        datasets,
        rows_to_table,
        project_folder=lambda: sab_projects.current.folder if sab_projects.current else None,
        default_folder=documents.made_default_folder,
        documents=lambda: usage_documents(documents, hooks, sab_projects, b.project_files),
        read_document=documents.read,
        grid_steps=lambda table: (
            describe_steps(grid.steps) if (grid := ws.grids.first_for(table)) is not None else []
        ),
    )
    # The APIs page: the library's APIs explored; a call sent opens in Structures, its origin the call.
    b.api_explorer = api_explorer = ApiExplorer(
        ws,
        b.apis,
        b.api_library,
        SpecSource(),
        b.blades,
        b.connections,
        b.connection_usage,
        structures,
        b.approvals,
        now=lambda: datetime.now(UTC).isoformat(timespec="seconds"),
        to_thread=asyncio.to_thread,
        reader=table_reader,
    )
    structures.rerun = api_explorer.run_again
    b.blades.web_call_saved.append(api_explorer.tables_changed)
    sab_projects.manifest_extras.append(lambda: {"structures": {"open": structures.open_paths()}})
    sab_projects.opened.append(structures.project_changed)
    # A table's connection swapped for another (its steps kept), and the code that named the old one.
    # What a connection is: its tables, listed and read one way for every kind; DuckDB SQL names them.
    b.connection_tables = ConnectionTablesService(
        ws,
        b.connections,
        b.catalogs,
        b.catalog_loading,
        table_reader.table_to_arrow_stream,
        aliases=lambda: (
            hooks.dataset_aliases() | ({sandbox_rules.NAME: b.sandbox_alias} if b.sandbox.folder() else {})
        ),
    )
    datasets.connection_sql = b.connection_tables
    b.connection_swap = ConnectionSwap(
        ws,
        datasets,
        b.connections,
        b.catalogs,
        b.catalog_loading,
        sab_projects,
        b.connection_usage,
        table_reader,
        read_document=documents.read,
        write_document=lambda path, text: documents.write(path, text, True),
        open_documents=lambda: hooks.documents(),
        ask_window=lambda command, args: b.workbench_window.ask(command, args, "app"),
    )
    # What the open project uses, one answer (services/project_scope.py ProjectUse): its tables and documents,
    # the connections it uses and where; the ERD draws only its tables by default (the owner, 2026-11-17).
    b.project_use = ProjectUse(
        UseSources(
            project=lambda: sab_projects.state().get("project"),
            documents=lambda: usage_documents(documents, hooks, sab_projects, b.project_files),
            read=documents.read,
            open_tables=lambda: {i.name for i in b.store.all()},
            connections=b.blade_store.all,
            references=b.connection_usage.references,
            api_text=lambda folder: LocalApiFiles.read(str(Path(folder) / local_api_rules.FILE)),
            inside=_inside,
            code_texts=ProjectFiles.code_texts,
            known=lambda: [h.name for h in b.connections_here()] + list(b.shared_catalog.catalogs()),
        )
    )
    b.project_documents = b.project_use.documents
    b.project_tables = ProjectTables(b.models, b.project_documents)
    # A connection deleted: the relationships its tables held go from the ones in use (saved sets stay).
    b.blades.connection_removed.append(
        lambda name, who: b.models.forget_connection(name, set(b.connection_swap.tables_of(name)), who)
    )


# ----- the shared catalog, code files that follow a change, the project's scope -----


def _connections_here(b: Built) -> list[Here]:
    """This computer's connections that have tables (never a key vault), for the shared catalog."""
    found = []
    for blade in b.blade_store.all():
        if blade.web_call or connection_rules.connection_kind(blade.kind, blade.template) is None:
            continue
        kind = connection_table_rules.tables_kind(
            blade.kind, blade.template, blade.dialect, blade.catalog_language, blade.tags, blade.code
        )
        if kind is not None:  # never a key vault: it has no tables
            found.append(Here(blade.name, kind, str(blade.template or "")))
    return found


def _shared_catalog_part(b: Built) -> None:
    """The shared catalog (the owner, 2026-11-17): the library's catalog/<connection>.json, kept by what
    happens here and read again when the user's pulls change it. The app never runs git."""
    library_folder, blades, sab_projects, models = b.library_folder, b.blades, b.sab_projects, b.models
    b.connections_here = partial(_connections_here, b)
    b.shared_catalog = shared_catalog = SharedCatalog(
        b.ws,
        CatalogFiles(b.library_files(), library_folder.ensure),
        b.connections_here,
        b.catalogs.listing_rows,
        lambda: models.model,
        today=lambda: datetime.now(UTC).date().isoformat(),
        now=lambda: datetime.now(UTC).isoformat(timespec="seconds"),
        project=b.project_use.catalog_use,
    )
    shared_catalog.load()
    b.library.catalog_info = shared_catalog.info
    b.project_tables.shared = shared_catalog.model

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
    b.code_files = CodeFiles(
        b.ws,
        lambda: (
            sab_projects.current.folder if sab_projects.current else None,
            str(library_folder.root) if b.persist else None,
        ),
        code_file_disk.stamp,
        code_file_disk.file_hash,
        # The open project's structure files too (a structure's tab follows its file), never the library's.
        lambda folder: code_file_disk.code_files_in(
            folder, structures=bool(sab_projects.current and folder == sab_projects.current.folder)
        ),
        code_file_disk.resolve,
        b.settings.file_watch_seconds,
    )
    b.project_scope = ProjectScope(
        sab_projects, b.archive, b.library, b.connections, on_saved=b.catalog_loading.saved
    )
    b.code_files.listeners.append(b.project_scope.saw)  # a made file saved by hand is marked so
    # A structure's tab follows its file as a script does (its hash; its Save said to every window).
    b.structures.hash_of = b.code_files.hash_now
    b.structures.touched = b.code_files.touched


# ----- the variables, Find connections, app registrations, Set up this computer -----


def _variables_part(b: Built) -> None:
    """The Variables page: this computer's variables (never a project's): the shareable file and the local
    values; their values given to this server's environment, so what it runs and starts reads them."""
    ws, state_dir, library_folder, blade_store, blades = (
        b.ws,
        b.state_dir,
        b.library_folder,
        b.blade_store,
        b.blades,
    )
    variables_file = VariableFiles(b.library_files(), library_folder.ensure)
    if b.persist:
        # Once: this computer's stores from before the library, written as library files (said on the page).
        moved = library_folder.migrate(
            state_dir, blade_store, variables_file, datetime.now(UTC).date().isoformat()
        )
        b.library.notice("computer", library_rules.computer_migration_words(moved["moved"], moved["backup"]))
        # Once: the library's tangs/ (the old name, 2026-11-17) as relationship-sets/ (said on the page).
        sets = library_folder.move_relationship_sets(state_dir, datetime.now(UTC).date().isoformat())
        b.library.notice("computer", library_rules.sets_migration_words(sets["moved"], sets["backup"]))

    async def save_variable_blade(data: dict[str, Any], previous: str, who: str) -> Any:
        saved = await blades.save(data, previous, who)
        b.catalog_loading.saved(str(saved["name"]))
        return saved

    b.variables = variables = Variables(
        ws,
        variables_file,
        VariableKeyring(),
        ProcessEnvironment(),
        blade_store,
        save_variable_blade,
        documents=lambda: usage_documents(b.documents, b.hooks, b.sab_projects, b.project_files),
        read=b.documents.read,
        run_settings=b.script_runs,
        kernels=b.workbench.kernel_count,
        vault_values=b.vault_values,
        remembered=blades.remembered,
        renamed_notes=b.kept_vault_names.notes,
    )
    # One name, one variable: the vaults' names given out around the user's own variables.
    b.kept_vault_names.vaults = blade_store.all
    b.kept_vault_names.defined = variables.defined_names
    b.connections.variable_check = variables  # a Test's ${NAME} checked first (12.7)
    # Find connections on this computer (the owner, 2026-11-20): the known tools' files and the hint scan of
    # the app settings folders, read-only, on the user's click; never this app's own state folder or library.
    b.found_connections = FoundConnections(
        ws,
        ConnectionFinder(
            home=b.settings.find_home,
            system=b.settings.find_system,
            skip=lambda: (state_dir, library_folder.root),
        ),
        TEMPLATES,
        blades,
        lambda data, who: b.connections.save(data, None, who),
        variables,
        b.approvals,
    )
    b.app_registrations = _app_registrations(
        ws, b.connections, blade_store, library_folder, variables, b.catalogs.places
    )
    b.datasets.variables = variables  # a query's ${NAME}: a bound parameter; a path's, read here
    b.structures.variables = variables
    b.api_explorer.variables = variables
    if b.persist:
        _variables_once(state_dir, b.library, variables)
    # The Environment (the owner, 2026-11-21/22): everything the project holds (services/environment.py).
    b.sessions = Sessions(b.processes, b.store, b.live)
    # One Python per project (the owner, 2026-11-21): the project's own .venv, made in the background, and
    # the one session every document of the project runs in (the Workbench's; ended when the project changes).
    b.project_python = project_python = ProjectPython(
        ws, environment_files, make_venv, b.settings.project_venv
    )
    project_python.end_session = b.workbench.end_session
    project_python.session_kernel = b.workbench.session_kernel
    project_python.forget_environment = b.documents.forget_environment
    b.workbench.project = project_python.session
    b.workbench.moved_environment = project_python.moved
    b.environment = Environment(
        ws,
        sources_from(
            datasets=b.datasets, sab_projects=b.sab_projects, workbench=b.workbench, sessions=b.sessions,
            structures=b.structures, settings=variables, cards=b.cards, models=b.models,
            document_paths=lambda: usage_documents(b.documents, b.hooks, b.sab_projects, b.project_files),
            read=b.documents.read, project_names=b.project_files.names, project_file=b.project_files.read,
            remove_file=environment_files.remove_structure_file, touched=b.code_files.touched,
        ),
        ProjectLibraries(environment_files),
        b.approvals,
        project_python,
    )  # fmt: skip
    b.live.listeners.append(b.environment.heard)
    # Shared projects: each one's connections that do not work here, and one opened that only works here.
    b.shared_projects = SharedProjects(
        b.project_explorer.shared_folder,
        b.project_explorer.where,
        ExplorerFiles.scan,
        b.project_use.named_in,
        lambda: [h.name for h in b.connections_here()],
        blade_store.get,
        blade_store.secret_status,
        partial(_project_notice, b),
    )
    # Set up from the meta store: what this computer needs before the team's connections work.
    b.library_setup = LibrarySetup(
        ws,
        blades,
        blade_store.secret_status,
        lambda: variables.listing()["variables"],
        b.connections,
        b.shared_projects.listing,
    )


# ----- shared projects on the checklist, and the Data Explorer -----


async def _project_notice(b: Built, said: str) -> None:
    """A notice about the open project, said once on the page (the library's notices)."""
    b.library.notice("project", said)
    await b.live.broadcast({"type": "library_notice", "text": said})


def _setup_and_explorer(b: Built) -> None:
    """Shared projects (said once when one's connections only work here, on the checklist when not set up
    here), and the Data Explorer: one search over the connections and their catalogs, the open tables, the
    variables and the blades, Structures' documents and paths, APIs' web calls that return a table."""
    b.sab_projects.opened.append(b.shared_projects.opened)
    b.explorer = _explorer(
        b.ws, b.datasets, b.connections, b.connection_tables, b.catalogs, b.catalog_loading, b.shared_catalog,
        b.variables, b.blades, b.structures,
    )  # fmt: skip


# ----- the project's sandbox and its local sandbox API -----


def _sandbox_part(b: Built) -> None:
    """The project's sandbox (domain/sandbox.py): the data a local sandbox API reads and writes, mocked as the
    client of the connection each table came from; [Sandbox].orders in DuckDB SQL; a Catalog section."""
    ws, datasets, connections, connection_tables = b.ws, b.datasets, b.connections, b.connection_tables

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
        body = await b.table_cells.view(name)
        return table_reader.arrow_stream_to_table(body, b.settings.max_dataset_bytes)

    async def sandbox_connection_table(name: str, place: Place) -> Any:
        kept, _ = await connection_tables.read(name, place)
        return kept.read.table

    async def sandbox_show(name: str, table: Any, follow: bool, words: str) -> dict[str, Any]:
        # Its origin: the sandbox table (its lineage and its read-only cell's load name [Sandbox].<table>).
        table_name = name.removeprefix(sandbox_rules.GRID_PREFIX)
        sql = f"SELECT * FROM [{sandbox_rules.NAME}].{table_name}"  # noqa: S608 (a checked table name)
        origin = TableOrigin("sandbox", connection=sandbox_rules.NAME, sql=sql, filename=words)
        return await datasets.store_table(name, table, "sandbox", False, "user", follow=follow, origin=origin)

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
                return [str(c) for c in b.shared_catalog.table(connection, name).get("primary_key") or []]
            except (LookupError, ValueError):
                continue
        return []

    def sandbox_ignore(folder: str) -> None:
        b.archive.write_state(folder, APP_IGNORE_FILE, APP_GITIGNORE.encode("utf-8"))
        sandbox_gitignore(folder)  # the rows' folder, sandbox/ at the project's top

    b.sandbox = sandbox = Sandbox(
        ws,
        lambda: b.sab_projects.current.folder if b.sab_projects.current is not None else None,
        SandboxFiles,
        SourcesFrom(
            sandbox_grid_view,
            sandbox_connection_table,
            datasets.read_file,
            sandbox_show,
            sandbox_client,
            structure_fn=b.structures.records_table,
            view_rows_fn=partial(grid_view_rows, ws),
            connections_fn=sandbox_connections,
            key_fn=sandbox_key,
        ),
        b.approvals,
        lambda sql: duckdb_grammar().parse(sql),
        ignore=sandbox_ignore,
    )
    b.sandbox_alias = SandboxAlias(sandbox)

    def sandbox_released(message: Mapping[str, Any]) -> None:
        """A project closed: its sandbox's file let go (one process at a time holds a DuckDB file, so
        sandbox_connections.py can run on it outside the app)."""
        if message.get("type") == "project_changed" and sandbox.folder() is None:
            sandbox.close()

    b.live.listeners.append(sandbox_released)
    # The Sandbox as a connection (the owner, 2026-11-21): its card on the Connections page and its colour.
    b.connection_usage.extra_cards = lambda: [c for c in [sandbox.card()] if c is not None]
    b.connection_colours.fixed = lambda: (
        [(sandbox_rules.NAME, sandbox_rules.COLOUR)] if sandbox.folder() else []
    )
    # The project's local sandbox API (API.py): hosted in a process of its own that gets only the sandbox.
    b.local_api = LocalApi(
        ws,
        sandbox.folder,
        LocalApiFiles(),
        api_runs.start,
        sandbox,
        b.approvals,
        data_url=lambda key: f"http://127.0.0.1:{b.port}/sandbox/data/{key}",
        catalog=b.catalogs,
        publish=publish_api,
    )
    b.explorer.register("sandbox", explorer_providers.sandbox_provider(sandbox.names_and_columns))
    # Every API's actions through api_adapter (Plans/api-adapter.plan.md): the library's and the local one's.
    b.actions = Actions(
        ws,
        b.api_explorer,
        b.local_api,
        ApiFiles(),
        sandbox.folder,
        b.approvals,
        lambda: datetime.now(UTC).date().isoformat(),
        hooks=b.hooks,
        api_adapter=api_adapter,
        adapter_text=lambda: Path(api_adapter.__file__).read_text(encoding="utf-8"),
        changed=b.code_files.touched,
        show=lambda path, at: b.workbench_window.ask(
            "file.openCell" if "cell" in at else "file.openAt", {"path": path, **at}, "app"
        ),
        stats=b.call_stats,
    )
    b.local_api.learned = b.actions.local_learned  # Try it fills its form from the learned shape


# ----- the app's own life: what is open, extensions, the Team box, sharing, updates -----


def _app_life(b: Built) -> None:
    ws, live, state_dir, state_file, approvals = b.ws, b.live, b.state_dir, b.state_file, b.approvals
    # The update check (the one request that leaves the computer, the owner's call) and Update to X.
    failure_note = state_file("update_failed.json")
    # Extensions (the Extensions page): the installed ones found once, at start; Install and Remove hand
    # over to the update's helper, and each update keeps the installed ones (`--with`).
    b.update_helper, b.extensions = _extensions(
        ws, live, approvals, state_dir, state_file, b.on_extensions, b.on_shutdown, b.blades.install
    )
    # Settings' Team box: one GitHub repository for the team library and its projects/ (team.json: the team
    # joined, the folders before it, a step kept over Install's restart). The GitHub work is an extension's.
    b.team = _team(
        ws, b.hooks, b.library, b.project_explorer, b.library_setup, file_manager, approvals, b.extensions,
        state_dir, state_file,
    )  # fmt: skip
    # Share a running app with your organization (Microsoft Dev Tunnels; the third way data leaves this
    # computer, on the user's click): devtunnel in the state folder's devtunnel/, got on the first share.
    b.sharing = _sharing(ws, b.hooks, approvals, state_dir, b.port)
    open_work = partial(
        what_is_open,
        lambda: [{"grid": g.id, "name": g.dataset} for g in ws.grids.all() if b.store.get(g.dataset)],
        live.workbench_open,
        lambda: b.workbench_window.ask("documents", {}, "app"),
        b.hooks.unsaved,
        b.workbench.kernel_count,
    )
    b.updates = _updates(
        ws, live, b.settings, b.update_helper, b.extensions, approvals, open_work, failure_note,
        state_file, b.on_shutdown,
    )  # fmt: skip


# ----- the editors' intelligence, the Scripts IDE, context.md and Launch Claude, the modes -----


def _editors_and_claude(b: Built) -> None:
    ws, state_dir, sab_projects, live = b.ws, b.state_dir, b.sab_projects, b.live
    # Launch Claude: Claude Code in the user's terminal, or Claude Desktop, found wherever it is installed.
    standin = b.settings.claude_standin
    b.claude_files = ClaudeFiles(state_dir / "claude", b.state_file("claude.json"))
    b.agent = AgentService(ws, b.approvals, b.tickets)
    catalog_of = partial(_catalog_of, b.catalogs)
    used_in = b.project_use.places
    # One Jedi world and one set of linters: the editors' intelligence's, and the Scripts IDE's (never a
    # second).
    jedi_world = JediWorld()
    linters = Linters(run_text)
    b.intellisense = Intellisense(
        ws,
        kernel_intel.answer,
        jedi_world,
        ProjectModules(),
        linters,
        kernel_of=b.workbench.kernel_or_none,
        project_folder=lambda: (sab_projects.state().get("project") or {}).get("folder"),
        blades=lambda: b.blades.listing()["blades"],
        variables=lambda: b.variables.listing()["variables"],
        structures=lambda: sorted({str(f.get("name")) for f in b.structures.files()}),
        dialect_of=lambda name: next(
            (x.dialect for x in b.blade_store.all() if x.name.casefold() == name.casefold()), None
        ),
        read_file=lambda path: b.documents.read(path)[0],
        sandbox_clients=b.sandbox.mock_names,
        sandbox_tables=b.sandbox.table_columns,
        sandbox_mocks=b.sandbox.mock_dialects,
    )
    b.script_ide = ScriptIde(
        ws,
        ScriptCode(run_text),
        jedi_world,
        linters,
        tree=lambda: b.project_scope.tree("scripts"),
        touched=b.code_files.touched,
        library=lambda: (
            (str(b.library_folder.root), code_file_disk.code_files_in(str(b.library_folder.root)))
            if b.persist
            else (None, [])
        ),
        tables=b.table_cells.listing,
        trash=file_manager.trash,  # Delete: the system's trash, the user's own
        library_roots=lambda: tuple(  # Python's own folders: a library's source, read-only
            dict.fromkeys(
                p
                for k in ("stdlib", "platstdlib", "purelib", "platlib")
                if (p := sysconfig.get_paths().get(k))
            )
        ),
    )
    b.blades.lint = b.intellisense.lint  # the blade IDE's Problems, for the agent (blades_problems)
    b.modes = Modes(
        extension_modules.modes,
        lambda: sab_projects.current.folder if sab_projects.current is not None else b.projects.opened,
        b.projects.type_of,
        extension_modules.areas,
        sab_projects.setting,
        sab_projects.set_setting,
    )
    b.context_md = context_md = ContextMd(
        ws,
        b.claude_files,
        version=__version__,
        project=lambda: sab_projects.state().get("project"),
        connections=lambda: b.connection_usage.overview()["connections"],
        colour_of=b.connection_colours.colour_of,
        catalog=catalog_of,
        used_in=used_in,
        origin_of=b.datasets.origins.get,
        relationships=b.models.current,
        variables=lambda: b.variables.listing(),
        documents=lambda: b.project_scope.documents(),
        windows=lambda: {
            "home": live.workspace_open(),
            "front": b.agent.active_grid,
            "workbench": live.workbench_open(),
            "kernels": b.workbench.running_documents(),
            "blades": live.catalog_open(),
        },
        changes=lambda: live.changes,
        apis=b.api_explorer.listing,
        structures=b.structures.listing,
        shared=lambda: b.shared_catalog.listing(),
        access=b.app_registrations.access,
        gates=b.modes.gates,
    )
    b.claude = Claude(
        ws,
        StandinFinder(standin) if standin else ClaudeFinder(),
        RecordingStarter(standin.with_suffix(".launches.jsonl")) if standin else ClaudeStarter(),
        b.claude_files,
        version=__version__,
        home=str(Path.home()),
        environ=dict(os.environ),
        commands=own_command,
        project=lambda: sab_projects.state().get("project"),
        connections=lambda: b.connections.listing()["connections"],
        documents=lambda: b.project_scope.documents()["documents"],
        context_md=context_md,
    )


# ----- the project's outline, the file dialogs, the server's life, the analyses -----


def _saved_dashboards(b: Built) -> list[dict[str, Any]]:
    """The open project's saved dashboards: each one's name and its last version's cards."""
    out = []
    for listed in b.dashboards.names():
        body = b.dashboards.read(str(listed["name"])) or {"versions": []}
        last = body["versions"][-1] if body["versions"] else {}
        out.append({"name": listed["name"], "cards": last.get("cards") or []})
    return out


def _picker_places(b: Built) -> list[dict[str, str]]:
    """The page's own picker's quick places: the system's, then the projects folder and the library."""
    found = folder_places()
    for name, kind, folder in (
        ("Projects", "projects", b.project_explorer.folder()),
        ("Library", "library", str(b.library_folder.root)),
    ):
        if is_folder(folder):
            found.append({"name": name, "path": folder, "kind": kind})
    return found


async def _before_stop(b: Built) -> str:
    """Before the server stops: the open project's unsaved changes saved as Autosave does; with Autosave
    off, the stop waits (its words)."""
    current = b.sab_projects.current
    if current is None or not b.sab_projects.dirty():
        return ""
    if not current.autosave:
        return "the open project has unsaved changes and Autosave is off"
    try:
        await b.sab_projects.save({}, "autosave")
    except Exception as error:
        return f"the open project could not be saved: {error}"
    return ""


def _outline_dialogs_and_life(b: Built) -> None:
    ws, settings, sab_projects = b.ws, b.settings, b.sab_projects
    # The project's outline, ARCHITECTURE.md: its two seams wired to the ERD's tables in the project
    # (services/relationship_scope.py) and the connection cards' portability (domain/portability.py).
    b.project_outline = project_outline = ProjectOutline(
        ws,
        b.archive,
        project=lambda: sab_projects.state().get("project"),
        mode=lambda: b.modes.active()["mode"],
        connections=lambda: b.connection_usage.overview()["connections"],
        usage=b.connection_usage.usage,
        table_cells=b.table_cells.listing,
        origin_of=b.datasets.origins.get,
        kernel_document=b.workbench.document_of,
        relationships=b.models.current,
        dashboards=partial(_saved_dashboards, b),
        run_settings=b.script_runs.settings,
        app_pages=lambda path, text: b.hooks.app_pages(path, text),
    )
    project_outline.used_tables = BothTables(b.project_tables.used, project_outline.used_tables)
    project_outline.portability = CardPortability(lambda: b.connection_usage.overview()["connections"])
    # The system's own file dialog on the user's click (server/dialog_runner.py), and the page's own picker's
    # quick places and recent folders per kind of pick (dialogs.json: paths only).
    b.file_dialogs = FileDialogs(
        dialog_runner.DialogRunner(),
        JsonFile(b.state_file("dialogs.json")),
        partial(_picker_places, b),
        is_folder,
    )
    # The server's life follows the app's windows (services/lifecycle.py): before it stops, the open
    # project's unsaved changes are saved as Autosave does; with Autosave off, the stop waits.
    b.lifecycle = Lifecycle(
        windows=b.live.windows,
        busy=lambda: ["a VS Code window"] if b.live.openers() else [],
        before_stop=partial(_before_stop, b),
        stop=b.on_shutdown,
        grace=settings.life_grace_seconds,
        idle=settings.life_idle_seconds,
        start_grace=settings.life_start_grace_seconds,
    )
    b.grid_service = GridService(ws, b.datasets.origins.get)
    b.analysis = Analysis(ws, b.verifier)
    b.key_finder = KeyFinder(ws)
    b.tie_out = TieOut(b.compares)


# ----- exports: a document as one script, a local sandbox API for its framework target -----


_CARRIED_FILES = {"sab_excel": "sab_excel.py", "adapter": "adapters/adapter.py"}


def _carried_file(module: str) -> str | None:
    """The text of one of the scaffold's files the app holds (what an exported script carries inline)."""
    place = _CARRIED_FILES.get(module)
    return (Path(__file__).parent / place).read_text(encoding="utf-8") if place else None


def _exports(b: Built) -> None:
    ws, local_api, sandbox = b.ws, b.local_api, b.sandbox
    # Export as one Python script: the document's cells, its connections' own code, ruff's check.
    b.script_exports = ScriptExports(
        ws,
        b.blade_store,
        read_document=b.documents.read,
        write_document=b.documents.write,
        arrange=b.table_cells.arrange,
        lint=script_lint,
        folder_of=lambda path: str(Path(path).expanduser().parent),
        join=lambda folder, name: str(Path(folder) / name),
        inline=b.apis.inline,  # an API_<name>.py the document imports travels inside the export
        carried=_carried_file,  # sab_excel.py or adapter.py, for a blade that imports it by that name
    )
    # A local sandbox API exported for its framework target: the real connections' own code.
    b.api_export = api_export = ApiExport(
        ws,
        sandbox.folder,
        lambda folder: LocalApiFiles.read(str(Path(folder) / local_api_rules.FILE)),
        lambda: Path(api_runtime.__file__).read_text(encoding="utf-8"),
        b.script_exports,
        ExportFolder(sandbox.copy_now),
        b.project_scope.edited_in,
        b.approvals,
        adapter_text=lambda: Path(adapter.__file__).read_text(encoding="utf-8"),
        api_adapter_text=lambda: Path(api_adapter.__file__).read_text(encoding="utf-8"),
    )
    for extension in b.on_extensions:
        for raw in getattr(extension, "API_TARGETS", ()) or ():
            api_export.registry.add(api_target_rules.from_extension(raw, str(getattr(extension, "ID", ""))))
        for raw in getattr(extension, "API_PATTERNS", ()) or ():  # the endpoint wizard's patterns
            local_api.patterns.add(api_pattern_rules.from_extension(raw, str(getattr(extension, "ID", ""))))
    b.scaffold = _scaffold(b)
    local_api.target_ids = api_export.registry.ids
    local_api.targets = lambda: [{"id": t.id, "label": t.label} for t in api_export.registry.targets.values()]


# ----- what the doors are given -----


def _scaffold(b: Built) -> Scaffold:
    """The project scaffold kept as the user works (services/scaffold.py): what each made file is made of."""

    def project() -> tuple[str, str] | None:
        current = b.sab_projects.current
        return (current.folder, current.name) if current is not None else None

    def inside(path: str | None) -> bool:
        found = project()
        return found is not None and _inside(path, found[0])

    def variables() -> dict[str, str]:
        return {name: words for name, (words, _) in b.variables.sources().items()}

    def documents_using(name: str) -> list[str]:
        """The project's own documents that read the variable (never a file the scaffold made: its
        connections.py reads what the connections read, said by their sections)."""
        held = b.variables.sources().get(name)
        found = project()
        if held is None or found is None:
            return []
        out = []
        for what, path in held[1]:
            if not path or not inside(path):
                continue
            relative = os.path.relpath(os.path.realpath(path), os.path.realpath(found[0])).replace("\\", "/")
            if relative not in scaffold_rules.MADE:
                out.append(what)
        return out

    def structures() -> list[scaffold_rules.StructureGrid]:
        found = project()
        if found is None:
            return []
        out: list[scaffold_rules.StructureGrid] = []
        for grid in b.ws.grids.all():
            origin = b.datasets.origins.get(grid.dataset)
            if origin is None or origin.kind != "structure" or not inside(origin.path):
                continue
            relative = os.path.relpath(str(origin.path), found[0]).replace("\\", "/")
            if relative.lower().endswith(scaffold_rules.STRUCTURE_SUFFIXES):
                out.append(
                    scaffold_rules.StructureGrid(variable_name(grid.dataset), relative, origin.sql or "$")
                )
        return sorted(set(out), key=lambda s: s.variable)

    def endpoints(text: str) -> int:
        try:
            return len(local_api_rules.parse(text).endpoints)
        except Exception:
            return 0

    def contract(folder: str) -> dict[str, Any] | None:
        """The project type's contract.json, from the extension (packaged or a folder) that adds the type."""
        kind = b.projects.type_of(folder)
        holders = [*extension_modules.enabled(), *(f.module for f in extension_modules.folders().values())]
        for module in holders:
            if module is None:
                continue
            try:
                found = extension_modules.contract(module)
            except Exception:  # noqa: S112 (a broken contract.json: said on the Extensions page)
                continue
            if found is not None and found["type"] == kind:
                return found
        return None

    def names(folder: str) -> list[str]:
        """The project top's files and folders (a folder as `name/`), for the contract's deliverable."""
        try:
            return sorted(e.name + ("/" if e.is_dir() else "") for e in os.scandir(folder))
        except OSError:
            return []

    made = Scaffold(
        b.ws,
        project,
        ScaffoldFiles(),
        ScaffoldSources(
            used=b.project_use.connections,
            connections=b.script_exports.connections_code,
            adapter=lambda: Path(adapter.__file__).read_text(encoding="utf-8"),
            variables=variables,
            documents_using=documents_using,
            sandbox=b.sandbox.mirror,
            structures=structures,
            edited=b.project_scope.edited_in,
            touched=b.code_files.touched,
            endpoints=endpoints,
            contract=contract,
            names=names,
        ),
    )
    b.live.listeners.append(made.heard)
    return made


def _services(b: Built) -> Services:
    ws, workbench = b.ws, b.workbench
    return Services(
        settings=b.settings,
        ws=ws,
        datasets=b.datasets,
        file_watch=b.file_watch,
        code_files=b.code_files,
        grids=b.grid_service,
        profiles=Profiles(ws),
        analysis=b.analysis,
        analyze=Analyze(
            ws, b.grid_service, b.datasets, b.analysis, b.tie_out, b.key_finder, b.cards, b.blades
        ),
        regression=Regression(ws),
        timeseries=TimeSeries(ws),
        sql=SqlBox(ws, b.datasets, table_reader),
        exports=Exports(ws, export_writer, b.tickets, now=lambda: datetime.now(UTC)),
        codes=CodeService(ws, b.verifier),
        cards=b.cards,
        inbox=Inbox(ws),
        agent=b.agent,
        sessions=b.sessions,
        catalogs=b.catalogs,
        blades=b.blades,
        connections=b.connections,
        found_connections=b.found_connections,
        connection_usage=b.connection_usage,
        connection_slots=b.slots,
        call_stats=b.call_stats,
        changes=b.changes,
        apis=b.apis,
        structures=b.structures,
        api_explorer=b.api_explorer,
        actions=b.actions,
        catalog_loading=b.catalog_loading,
        vault_names_at_start=b.vault_names_at_start,
        connection_tables=b.connection_tables,
        folders=Folders(
            folder_listing,
            lambda where: ensure_own_folder(where, b.settings.workbench_dir),
            places=b.file_dialogs.places,
            make_folder=make_folder,
        ),
        file_dialogs=b.file_dialogs,
        workbench=workbench,
        models=b.models,
        project_tables=b.project_tables,
        finder=Finder(ws, b.models),
        library=b.library,
        library_setup=b.library_setup,
        team=b.team,
        sharing=b.sharing,
        sandbox=b.sandbox,
        local_api=b.local_api,
        api_export=b.api_export,
        scaffold=b.scaffold,
        shared_catalog=b.shared_catalog,
        app_registrations=b.app_registrations,
        keys=b.key_finder,
        compares=b.compares,
        tie_out=b.tie_out,
        snapshots=Snapshots(ws),
        workbench_window=b.workbench_window,
        intellisense=b.intellisense,
        script_ide=b.script_ide,
        debugger=Debugger(
            ws,
            lambda kernel: cast(
                "DebugKernel | None", workbench.kernel_or_none(kernel)
            ),  # server/kernels.py's
            workbench.kernel_for,
            workbench.document_of,
        ),
        table_cells=b.table_cells,
        modes=b.modes,
        switched_on=b.on_extensions,
        hooks=b.hooks,
        data_export=b.data_export,
        documents=b.documents,
        project_files=b.project_files,
        export_writer=export_writer,
        process_event=b.process_event,
        session_log=b.session_log,
        variables=b.variables,
        environment=b.environment,
        project_python=b.project_python,
        explorer=b.explorer,
        connection_swap=b.connection_swap,
        navigation=Navigation(ws, JsonFile(b.state_file("rail.json"))),
        script_runs=b.script_runs,
        connection_colours=b.connection_colours,
        beta=b.beta,
        updates=b.updates,
        extensions=b.extensions,
        lifecycle=b.lifecycle,
        desktop=Desktop(SystemShell(info_file_path()), ws.audit, qt_version()),
        claude=b.claude,
        context_md=b.context_md,
        lineage=Lineage(
            ws,
            b.hooks,
            b.datasets.origins,
            b.documents.read,
            b.project_files,
            workbench.lineage_values,
            kernel_for=workbench.kernel_for,
        ),
        projects=b.projects,
        sab_projects=b.sab_projects,
        project_explorer=b.project_explorer,
        project_scope=b.project_scope,
        project_outline=b.project_outline,
        script_exports=b.script_exports,
        live=b.live,
        workers=b.workers,
    )
