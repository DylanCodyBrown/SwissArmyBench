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
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol


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
