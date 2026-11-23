"""What an extension hands the base's services once everything is built (the composition root's late binding).

The base's services are built first (bootstrap.py); each extension that is on builds its own from them when
its routes are mounted, and fills in here what the base asks of it. With none of them on, every hook keeps its
default: nothing held. The base never names the extension that fills one.

  documents         the files the Workbench windows hold open (the Connections page's references)
  unsaved           the titles of open documents holding unsaved changes (asked before an update)
  held              an open document as its window holds it now, saved or not (None: not held)
  app_document      the Workbench's open and save of an app's own file (`.stapp.json`)
  project_app       a new base project's own app files and requirements ({} with none)
  app_pages         an app's pages and the cells their blocks link (the project's outline)
  team              GitHub sync for Settings' Team box (services/team.py TeamSync; None: its Install offered)
  share_targets     the app kinds that can be shared with the organization (services/sharing.py ShareTarget:
                    an app's own 127.0.0.1 port opened and closed), by kind ({}: nothing to share)
  sharing           the base's Sharing, for a target whose app stops (its link ends with it: app_stopped)
  canvas_put        a widget put on a canvas page (Build on the APIs page)
  dataset_aliases   a project's one dataset connection name that resolves through a setting of its own (a
                    Power BI project's Read Power BI from): DuckDB SQL and a kernel's %%dax cell follow it
  api_uses          the canvases' widget instances and Events that name a local sandbox API's endpoint
                    (Payload shapes; [] with no extension making canvases)
  query_hints       tables worth one COUNTROWS per dataset name (an app registration's access report)
  project_code      the code a project folder's canvases place, as (why, code): what the project needs
                    installed as it opens (services/project_python.py ProjectInstalls; [] with none on)

Seams, below, is the other direction (craft review 2026-11-22): what the base offers an extension's
composition root, typed, so a base rename is a type error there instead of a feature going quiet:

  project_folder    the open project's folder (None: none open)
  opened_folder     the folder a project was last made or opened in (the mode reads its type), and set_opened
  project_private   whether the open project is marked private (nothing of it sent anywhere)
  project_opened    the listeners told when a project is opened or made (folder, its manifest's extra)
  project_saved     the listeners told when the open project is saved (its folder)
  live_listeners    the listeners every live notice is told to, as it is sent
  variable_names    this computer's variables, by name (never a value)
  connection_tables what a connection's tables are (services/connection_tables.py): names, kind, places,
                    listed, read_named, prepare
  local_api         the project's local sandbox API's endpoints and pairings (services/local_api.py)
  actions           every API's actions as the canvas names them, and what a built app carries
  ws, settings      the shared ports every use case has (the audit log, the live notices, the workers, the
                    open tables) and the limits
  approvals         the one way the agent asks for the user's Allow (services/ports.py Approvals)
  hooks             the Hooks above, for the extension to fill
  extension         each extension's own services, by its id (its stop and tests read its own slot)
  process_event     a child process's start and end told to the beta log (kind, then the event)
  export_writer     rows as a file's bytes (adapters/export.py)
  datasets, blades, connections, variables, library, project_explorer, shared_catalog, models, compares,
  sab_projects, app_registrations
                    the base's services, each as the small port of what an extension calls (below)
  api_document      a library API's OpenAPI document and its source (the APIs explorer's document_of)
  used_tables       the tables the open project uses (None: no project open)
  document_python   the Python a document runs in (the Workbench's remembered environment; None: the app's)
  core_files        an export's adapter.py and connections.py for the connections named (the scaffold's)

server/app.py hands Seams, never the whole Services record, to each extension's `routes` and `stop`
(tests/test_extension_layers.py): a member an extension reads is declared here, so a base rename is a mypy
error in bootstrap's `_seams` (the base no longer fits its port) or in the extension (the port lacks it).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from swissarmybench.domain.app_registrations import Registration
from swissarmybench.domain.blades import Blade
from swissarmybench.domain.datasets import Opened
from swissarmybench.domain.relationships import Model
from swissarmybench.domain.table_cells import Origin
from swissarmybench.services.ports import Approvals
from swissarmybench.services.workspace import Workspace
from swissarmybench.settings import Settings


class AppDocument(Protocol):
    """An app's own file in the Workbench: read for a window, written from what the window sends."""

    def open(self, text: str, full: str) -> dict[str, Any]: ...

    def write(self, body: dict[str, Any], path: str) -> str: ...


class DatasetAlias(Protocol):
    """A dataset connection name that is not a saved connection: what it reads now resolves through a
    project setting (Published, Local, the file). Its tables, a table read whole, DAX on it (Arrow tables)."""

    def words(self) -> str: ...

    async def tables(self) -> list[str]: ...

    async def read(self, table: str) -> Any: ...

    async def dax(self, query: str) -> Any: ...


def _none(*_: Any) -> Any:
    return None


def _no_list(*_: Any) -> list[str]:
    return []


@dataclass
class Hooks:
    documents: Callable[[], list[str]] = _no_list
    unsaved: Callable[[], list[str]] = _no_list
    held: Callable[[str], Any] = _none
    app_document: AppDocument | None = None
    project_app: Callable[[str], dict[str, Any]] = field(default=lambda name: {})
    # An app's file (its whole path, its text) as its pages, each with the cells its blocks link (the
    # document's whole path, the cell's number): the project's outline. None on here: no pages.
    app_pages: Callable[[str, str], list[tuple[str, list[tuple[str, int]]]]] = field(
        default=lambda path, text: []
    )
    # Settings' Team box: the repository's local copy, its new repository, pull and push (services/team.py
    # TeamSync). None: no extension syncs with GitHub here, and the box offers its Install.
    team: Any = None
    # The open project's dataset connection names that resolve through its own setting ({} with none).
    dataset_aliases: Callable[[], dict[str, DatasetAlias]] = field(default=lambda: {})
    # Share a running app (services/sharing.py): the kinds that can be; the base's Sharing for their stops.
    share_targets: dict[str, Any] = field(default_factory=dict)
    sharing: Any = None
    # Build's widget (services/actions.py): {"canvas"?, "page"?, "widget", "values", "wire"} put on a page,
    # answered {"canvas", "id"}. None: no extension makes canvases.
    canvas_put: Callable[[dict[str, Any], str], Awaitable[dict[str, Any]]] | None = None
    # The canvases' widget instances and Events naming an endpoint (services/local_api.py's Payload shapes).
    api_uses: Callable[[], list[dict[str, Any]]] = field(default=lambda: [])
    # Tables worth one COUNTROWS, per dataset name (a Power BI project's tables: its app registration report).
    query_hints: Callable[[], dict[str, str]] = field(default=dict)
    # The code a project folder's canvases place (their widgets'), as (why, code): what it needs installed.
    project_code: Callable[[str], list[tuple[str, str]]] = field(default=lambda folder: [])


# ===== what the base offers an extension (Seams) =====


class ConnectionTablesSeam(Protocol):
    """What a connection's tables are (services/connection_tables.py ConnectionTables)."""

    def names(self) -> list[str]: ...

    def kind(self, name: str) -> tuple[str, str]: ...

    async def places(self, name: str) -> list[Any]: ...

    async def listed(self, name: str, most: int = 500) -> list[str] | None: ...

    async def read_named(self, reference: str) -> Any: ...

    async def prepare(self, text: str) -> Any: ...


class LocalApiSeam(Protocol):
    """The project's local sandbox API (services/local_api.py LocalApi): its endpoints and their pairings."""

    def endpoint_names(self) -> list[str]: ...

    def endpoint_fields(self) -> dict[str, list[str]]: ...

    def paired(self) -> list[dict[str, Any]]: ...


class ActionsSeam(Protocol):
    """Every API's actions (services/actions.py Actions): as the canvas's one picker names them, and the files
    a built app carries."""

    def refs(self) -> list[dict[str, Any]]: ...

    def carried(self, used: str) -> dict[str, str]: ...


class OriginsSeam(Protocol):
    def get(self, name: str) -> Origin: ...


class DatasetsSeam(Protocol):
    """How a table arrives (services/datasets.py DatasetService), and where each open one came from."""

    @property
    def origins(self) -> OriginsSeam: ...

    async def store_table(
        self,
        name: str,
        table: Any,
        source_kind: str,
        new_grid: bool,
        who: str,
        query: str | None = None,
        follow: bool = False,
        opened: Opened | None = None,
        origin: Origin | None = None,
    ) -> dict[str, Any]: ...


class BladesSeam(Protocol):
    """The library's blades (services/blades.py BladeService)."""

    def get(self, name: str) -> Blade: ...

    def everything(self) -> list[Blade]: ...

    def summary(
        self, blade: Blade, everything: list[Blade] | None = None, pinned: set[str] | None = None
    ) -> dict[str, Any]: ...

    def starters(self) -> dict[str, Any]: ...


class ConnectionsSeam(Protocol):
    """The library's connections (services/connections.py ConnectionService)."""

    def listing(self) -> dict[str, Any]: ...

    def blade(self, name: str) -> tuple[Blade, str]: ...

    async def save(self, body: Any, previous: str | None, who: str = "user") -> dict[str, Any]: ...

    async def datasets(self, name: str, body: Any, live: bool | None = None) -> dict[str, Any]: ...

    async def open_table(self, name: str, body: Any, who: str) -> dict[str, Any]: ...

    async def read_query(self, name: str, sql: str, body: Any = None) -> Any: ...

    async def read_for_query(self, name: str, place: dict[str, str], pushed: Any, most: int) -> Any: ...


class VariablesSeam(Protocol):
    """This computer's variables (services/variables.py Variables); never a secret's value."""

    def listing(self, search: Any = None, source: Any = None) -> dict[str, Any]: ...

    def shareable(self) -> dict[str, str]: ...

    async def put(self, body: Any, who: str = "user") -> dict[str, Any]: ...

    async def resolve(self, text: str, where: str = "") -> str: ...


class LibrarySeam(Protocol):
    """The library folder (services/library.py Library)."""

    def folder(self) -> Any: ...

    def made(self) -> None: ...

    def info(self) -> dict[str, Any]: ...

    async def set_folder(self, body: Any, who: str = "user") -> dict[str, Any]: ...


class ProjectExplorerSeam(Protocol):
    """The projects folders (services/project_explorer.py ProjectExplorer)."""

    def shared_folder(self) -> str | None: ...

    async def set_folder(self, body: Any, who: str = "user") -> dict[str, Any]: ...


class SharedCatalogSeam(Protocol):
    async def refresh(self, who: str = "user") -> dict[str, Any]: ...


class ModelsSeam(Protocol):
    """The relationships in use (services/relationships.py Models)."""

    @property
    def model(self) -> Model: ...

    async def apply(self, model: Model, who: str) -> dict[str, Any]: ...


class ComparesSeam(Protocol):
    async def create(self, body: Any, who: str) -> dict[str, Any]: ...


class OpenProject(Protocol):
    @property
    def folder(self) -> str: ...


class ProjectsSeam(Protocol):
    """The open project (services/sab_projects.py SabProjects): its state, a new one, its own settings."""

    @property
    def current(self) -> OpenProject | None: ...

    def state(self) -> dict[str, Any]: ...

    async def new(self, body: Any, who: str = "user") -> dict[str, Any]: ...

    def setting(self, key: str) -> Any: ...

    async def set_setting(self, key: str, value: Any, who: str = "user") -> dict[str, Any]: ...


class RegistrationsSeam(Protocol):
    """The library's app registrations (services/app_registrations.py AppRegistrations)."""

    def names(self) -> list[str]: ...

    def get(self, name: str) -> Registration: ...

    async def check(self, name: str, who: str) -> dict[str, Any]: ...


ProjectOpened = Callable[[str, Mapping[str, Any]], Awaitable[None]]
ProjectSaved = Callable[[str], Awaitable[None]]


@dataclass
class Seams:
    project_folder: Callable[[], str | None]
    opened_folder: Callable[[], str | None]
    set_opened: Callable[[str | None], None]
    project_private: Callable[[], bool]
    project_opened: list[ProjectOpened]
    project_saved: list[ProjectSaved]
    live_listeners: list[Callable[[dict[str, Any]], None]]
    variable_names: Callable[[], list[str]]
    connection_tables: ConnectionTablesSeam
    local_api: LocalApiSeam
    actions: ActionsSeam
    ws: Workspace
    settings: Settings
    approvals: Approvals
    hooks: Hooks
    extension: dict[str, Any]
    process_event: Callable[..., None]
    export_writer: Any
    datasets: DatasetsSeam
    blades: BladesSeam
    connections: ConnectionsSeam
    variables: VariablesSeam
    library: LibrarySeam
    project_explorer: ProjectExplorerSeam
    shared_catalog: SharedCatalogSeam
    models: ModelsSeam
    compares: ComparesSeam
    sab_projects: ProjectsSeam
    app_registrations: RegistrationsSeam
    api_document: Callable[[str], tuple[dict[str, Any], dict[str, Any]]]
    used_tables: Callable[[], set[str] | None]
    document_python: Callable[[str], str | None]
    core_files: Callable[[list[str]], Awaitable[dict[str, Any]]]
