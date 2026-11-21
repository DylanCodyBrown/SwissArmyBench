"""What an extension hands the base's services once everything is built (the composition root's late binding).

The base's services are built first (bootstrap.py); each extension that is on builds its own from them when
its routes are mounted, and fills in here what the base asks of it. With none of them on, every hook keeps its
default: nothing held, nothing to stop, no canvas. The base never names the extension that fills one.

  documents         the files the Workbench windows hold open (the Connections page's references)
  unsaved           the titles of open documents holding unsaved changes (asked before an update)
  held              an open document as its window holds it now, saved or not (None: not held)
  canvas            an app's canvas by its id (lineage from a canvas block)
  read_trace        what a playing page noted of its blocks (lineage's values)
  kernel_stopped    a kernel stopped: what ran beside it stops too
  stop_orphans      the windows still open: what a closed window left running stops
  canvas_references a canvas's blocks that use a connection, from the cells found to use it
  app_document      the Workbench's open and save of an app's own file (`.stapp.json`)
  project_app       a new base project's own app files and requirements ({} with none)
  app_pages         an app's pages and the cells their blocks link (the project's outline)
  team              GitHub sync for Settings' Team box (services/team.py TeamSync; None: its Install offered)
  dataset_aliases   a project's one dataset connection name that resolves through a setting of its own (a
                    Power BI project's Read Power BI from): DuckDB SQL and a kernel's %%dax cell follow it
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from swissarmybench.services.workspace import NotFound


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


async def _nothing(*_: Any) -> Any:
    return None


def _no_canvas(app_id: str) -> Any:
    raise NotFound("Canvases are the Streamlit extension's: it is not installed here (Extensions: Install).")


@dataclass
class Hooks:
    documents: Callable[[], list[str]] = _no_list
    unsaved: Callable[[], list[str]] = _no_list
    held: Callable[[str], Any] = _none
    canvas: Callable[[str], Any] = _no_canvas
    read_trace: Callable[[str, str], str | None] = _none
    kernel_stopped: Callable[[str], Awaitable[Any]] = _nothing
    stop_orphans: Callable[[set[str]], Awaitable[Any]] = _nothing
    canvas_references: Callable[[str, str, str, Sequence[Any]], list[Any]] | None = None
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
