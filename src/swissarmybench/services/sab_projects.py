"""Projects as one file: the .sab (the owner, 2026-11-16; rules in domain/sab_files.py). For the home page,
the Workbench window and the agent alike.

  new       a project of its own, saved at once where the user named (the owner, 2026-11-16: "The first
            thing it should do is have the user save a project file"): a working folder in the system's
            temporary folder, starting with data.ipynb (services/projects.py makes it, with the tables
            open now, and their connections copied in from this computer's)
  open      a .sab unpacked into a working folder; each table read again from where it came from, as a
            grid with its steps; Visualizations, the relationships and the windows' layout as they were. A
            table that cannot come back (a connection this computer does not have, a file that moved,
            a notebook not run yet, rows not kept) says so, with the click that fixes it (fix). A folder
            (today's projects) opens too: it is its own working folder
  save      the .sab written again (atomically) from the working folder, the open tables, Visualizations
            and the model. A pasted or pushed table's rows go in only when ticked (keep_rows); the
            agent's save waits for the user's Allow when it would write rows. Never a password
  close     the tables, Visualizations and the model closed, the temporary working folder removed
  autosave  the user's switch, kept in project.json: on, a save a short while after each change, quietly
  scope     the open project's saved dashboards are its own (its working folder's .sab folder,
            domain/project_scope.py): each open, new and close tells the stores (scope). Connections, APIs,
            vaults, blades and variables are the library's (Plans/library.plan.md), whatever is open: an
            older project's own .sab/blades go into the library as it opens (adopt), and its next save
            leaves them out
  recent    the projects opened and saved, with their files' state (recent_projects.json)

Whether there are unsaved changes is worked out, not tracked: what a save would write (the tables, their
sources and steps, Visualizations, the model, the working folder's files) against what the last save or
open wrote, and the Workbench's own unsaved documents. Opening another project when that would lose work
asks first (Conflict), and only then. One project is open at a time (memory only).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Protocol

from swissarmybench.domain import sab_files as rules
from swissarmybench.domain.relationships import Model, TangError, read_tang, write_tang
from swissarmybench.domain.sab_files import GridEntry, Manifest, Source, TableEntry
from swissarmybench.domain.steps import ViewSettings, steps_from_json
from swissarmybench.domain.table_cells import Origin
from swissarmybench.services.agent import Approvals
from swissarmybench.services.charts import Cards
from swissarmybench.services.connections import ConnectionService
from swissarmybench.services.datasets import DatasetService
from swissarmybench.services.ports import BACKGROUND
from swissarmybench.services.projects import Projects
from swissarmybench.services.relationships import Models
from swissarmybench.services.workspace import Conflict, NotFound, Refused, Workspace

MAX_LAYOUT_CHARS: int = 400_000
WORKBENCH_SAVE_SECONDS: float = 60.0
AUTOSAVE: str = "autosave"  # who a quiet save is, in the audit log


class Archive(Protocol):
    """The .sab on disk and the working folders (adapters/sab_files.py)."""

    def full(self, path: str) -> str: ...

    def exists(self, path: str) -> bool: ...

    def folder_of(self, path: str) -> str: ...

    def is_folder(self, path: str) -> bool: ...

    def manifest(self, path: str) -> str: ...

    def unpack(self, path: str, special: set[str], name: str) -> tuple[str, str, dict[str, str]]: ...

    def new_folder(self, name: str) -> tuple[str, str]: ...

    def remove(self, root: str | None) -> None: ...

    def files(self, folder: str) -> list[tuple[str, int, float]]: ...

    def app_files(self, folder: str) -> list[tuple[str, int, float]]: ...

    def replace_manifest(self, target: str, text: str) -> None: ...

    def read_file(self, folder: str, relative: str) -> bytes: ...

    def read_text(self, path: str) -> str: ...

    def write_rows(self, folder: str, table: Any) -> str: ...

    def read_rows(self, path: str) -> Any: ...

    def scratch(self) -> str: ...

    def write(self, target: str, entries: list[tuple[str, bytes | str]]) -> str: ...


class Recent(Protocol):
    def all(self) -> list[dict[str, Any]]: ...

    def add(self, path: str, when: float) -> None: ...

    def remove(self, path: str) -> bool: ...


@dataclass
class Current:
    """The open project."""

    name: str
    folder: str  # its working folder (a folder project's own folder)
    path: str | None = None  # the .sab (None: not saved yet, or a folder project not saved as one)
    root: str | None = None  # the temporary folder to remove when it closes (None: a folder project)
    read_only: str | None = None  # why it cannot be saved here (a newer format)
    manifest: Manifest | None = None  # as last read or written: what this version does not know is kept
    keep_rows: dict[str, bool] = field(default_factory=dict)
    saved_key: str | None = None
    layout: dict[str, Any] = field(default_factory=dict)  # each window's: workbench, home, diagram
    unsaved: list[str] = field(default_factory=list)  # the Workbench's documents with unsaved changes
    problems: dict[str, dict[str, Any]] = field(default_factory=dict)  # tables not back, and their fix
    autosave: bool = False
    autosave_error: str | None = None  # the last quiet save that failed, in words
    waiting: dict[str, TableEntry] = field(default_factory=dict)  # their steps, for when they arrive
    serial: int = 0


def _now_text(now: float) -> str:
    return datetime.fromtimestamp(now, UTC).isoformat(timespec="seconds")


def _keep_rows(raw: Any) -> dict[str, bool]:
    if raw is None:
        return {}
    if not isinstance(raw, dict) or not all(
        isinstance(k, str) and isinstance(v, bool) for k, v in raw.items()
    ):
        raise ValueError('keep_rows is {"table": true or false}: keep its rows in the file.')
    return dict(raw)


class SabProjects:
    def __init__(
        self,
        ws: Workspace,
        archive: Archive,
        recent: Recent,
        datasets: DatasetService,
        connections: ConnectionService,
        cards: Cards,
        models: Models,
        projects: Projects,
        reader: Any,  # query_table(cursor, sql): a table's rows (adapters/datasets.py)
        approvals: Approvals,
        version: str,
        now: Callable[[], float],
        kernel_document: Callable[[str | None], str | None] = lambda kernel: None,
        ask_workbench: Callable[[str, dict[str, Any]], Awaitable[Any]] | None = None,
        scope: Callable[[str | None], Awaitable[None]] | None = None,
        adopt: Callable[[str, str], dict[str, Any]] = lambda folder, name: {},
        autosave_seconds: float = 2.0,
    ) -> None:
        self.ws = ws
        self._archive = archive
        self._recent = recent
        self._datasets = datasets
        self._connections = connections
        self._cards = cards
        self._models = models
        self._projects = projects
        self._reader = reader
        self._approvals = approvals
        self._version = version
        self._now = now
        self._kernel_document = kernel_document
        self._ask_workbench = ask_workbench
        # The stores that follow the open project (its connections, blades, dashboards): its working
        # folder, or None (this computer's own, with no project open).
        self._scope = scope
        # An older project's own connections and blades (.sab/blades) moved into the library (folder, name).
        self._adopt_blades = adopt
        self._autosave_seconds = autosave_seconds
        self._settling: str | None = None  # autosave: what a save would write, as last seen
        self.current: Current | None = None
        self._serial = 0
        self._asked: str | None = None  # a .sab another program asked to open (the page asks the user)
        self._busy = asyncio.Lock()
        datasets.stored.append(self._arrived)
        # What other features keep in project.json (Structures: the ones open), and what they do once a
        # project has opened (its open structures come back): each a key of the manifest's own.
        self.manifest_extras: list[Callable[[], dict[str, Any]]] = []
        self.opened: list[Callable[[str, Mapping[str, Any]], Awaitable[None]]] = []

    # ===== what is open, and whether a save would change anything =====

    def _source(self, name: str, keep: bool) -> Source:
        current = self.current
        origin = self._datasets.origins.get(name)
        sab_folder = self._archive.folder_of(current.path) if current and current.path else None
        return rules.source_of(
            origin,
            sab_folder or (current.folder if current else None),
            current.folder if current else None,
            self._kernel_document(origin.kernel),
            origin.place,
            origin.whole,
            keep,
        )

    def _tables(self) -> list[TableEntry]:
        """The open tables as the file says them (and the ones waiting to come back, as they were)."""
        current = self.current
        keep = current.keep_rows if current else {}
        found: list[TableEntry] = []
        for info in self.ws.store.all():
            grids = tuple(
                GridEntry(tuple(s.to_json() for s in g.steps), g.settings.to_json())
                for g in self.ws.grids.for_dataset(info.name)
            )
            found.append(
                TableEntry(
                    info.name, self._source(info.name, keep.get(info.name, False)), grids or (GridEntry(),)
                )
            )
        open_names = {t.name for t in found}
        if current is not None:
            found += [t for name, t in current.waiting.items() if name not in open_names]
        return found

    def _key(self) -> str:
        """What a save would write now, as text (the Workbench's layout aside: moving a tab is no change)."""
        current = self.current
        tables = [t.to_json() for t in self._tables()]
        files = self._archive.files(current.folder) if current else []
        files += self._archive.app_files(current.folder) if current else []
        model = self._models.model.to_json() if self._models.model.tables() else None
        return json.dumps([tables, self._cards.state_key(), model, files], default=str, sort_keys=True)

    def _has_work(self) -> bool:
        return bool(self.ws.store.all()) or self._cards.holds_cards or bool(self._models.model.tables())

    def dirty(self) -> bool:
        """Would something be lost if the project (or the loose work, with none open) closed now?"""
        current = self.current
        if current is None:
            return self._has_work()
        if current.unsaved:
            return True
        if current.path is None and current.saved_key is None:
            return self._has_work()
        return self._key() != current.saved_key

    def state(self) -> dict[str, Any]:
        """The open project (None), whether it has unsaved changes, its tables that need a fix, and the
        recent projects."""
        current = self.current
        project: dict[str, Any] | None = None
        keep = current.keep_rows if current is not None else {}
        tables = [
            {
                "name": t.name,
                "kind": t.source.kind,
                "from": t.source.label(),
                "needs_rows": t.source.needs_rows,
                "keep_rows": keep.get(t.name, False),
            }
            for t in self._tables()
        ]
        if current is not None:
            project = {
                "name": current.name,
                "path": current.path,
                "folder": current.folder,
                "temporary": current.root is not None,
                "dirty": self.dirty(),
                "read_only": current.read_only,
                "serial": current.serial,
                "tables": tables,
                "problems": list(current.problems.values()),
                "layout": current.layout,
                "unsaved_documents": current.unsaved,
                "autosave": current.autosave,
                "autosave_error": current.autosave_error,
            }
        return {
            "project": project,
            "loose": current is None and self._has_work(),
            # The open work with no project: what saving it as one would write (its rows' ticks).
            "loose_tables": tables if current is None else [],
            "recent": self._recent.all(),
            "asked": self._asked,
        }

    async def _changed(self) -> None:
        await self.ws.live.broadcast({"type": "project_changed", "serial": self._serial})

    def _full(self, path: str) -> str:
        """A path the user or the agent gave, whole (refused in words when it is not one)."""
        try:
            return self._archive.full(path.strip())
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None

    def _need(self) -> Current:
        if self.current is None:
            raise NotFound("No project is open.")
        return self.current

    def _unsaved_words(self) -> str:
        current = self.current
        if current is None:
            return "The open tables are not saved in a project"
        return f"{current.name} has unsaved changes"

    def _check_discard(self, body: dict[str, Any]) -> None:
        if body.get("discard") is not True and self.dirty():
            raise Conflict(f"{self._unsaved_words()}: save it first, or send discard: true to let them go.")

    # ===== clearing the workspace =====

    async def _clear(self, who: str) -> None:
        """Every table closed, Visualizations and the model emptied, the temporary working folder removed."""
        for info in list(self.ws.store.all()):
            await self._datasets.close(info.name, who)
        await self._cards.clear()
        if self._models.model.tables() or self._models.model.relationships:
            await self._models.replace(Model())
        if self.current is not None:
            await asyncio.to_thread(self._archive.remove, self.current.root)
        self.current = None
        await self._rescope()

    async def _library_from(self, folder: str, name: str) -> None:
        """A project's own connections and blades (from before the library) moved into it; said once."""
        done = await asyncio.to_thread(self._adopt_blades, folder, name)
        if done.get("words"):
            await self.ws.live.broadcast({"type": "library_notice", "kind": "project", "text": done["words"]})

    async def _rescope(self) -> None:
        """The stores follow the open project (or this computer's, with none open)."""
        if self._scope is not None:
            await self._scope(self.current.folder if self.current else None)

    # ===== new =====

    async def new(self, body: Any, who: str = "user") -> dict[str, Any]:
        """New project: {"path": where its .sab goes, "autosave"?, "discard"?}. It is saved there at once:
        a project is never without its file. With a project open that has unsaved changes, asks first
        (Conflict). The tables open now (with no project) go into it: its data.ipynb starts with them
        (their connections are the library's)."""
        body = body if isinstance(body, dict) else {}
        path = body.get("path")
        if not isinstance(path, str) or not path.strip():
            raise ValueError('A new project is saved first: send {"path": where its .sab goes}.')
        target = self._full(rules.with_suffix(path.strip()))
        name = rules.check_name(rules.name_of_file(target))
        if not self._archive.is_folder(self._archive.folder_of(target)):
            raise NotFound(f"The folder {self._archive.folder_of(target)} is not there.")
        if self.current is not None:
            self._check_discard(body)
        await self._make(name, body.get("app") is True, who)
        current = self._need()
        current.autosave = body.get("autosave") is True
        try:
            return await self.save({"path": target}, who)
        except BaseException:
            async with self._busy:
                await self._clear(who)  # never a project without its file
            await self._changed()
            raise

    async def _make(self, name: str, app: bool, who: str) -> None:
        """A project of its own in a new working folder (not saved yet: new and save write it)."""
        async with self._busy:
            if self.current is not None:
                await self._clear(who)
            root, folder = await asyncio.to_thread(self._archive.new_folder, name)
            parent = self._archive.folder_of(folder)
            try:
                named = folder[len(parent) :].strip("\\/")
                made = await self._projects.create(
                    {"folder": parent, "name": named, "app": app},
                    who,
                    remember=False,
                    rows=False,
                )
            except BaseException:
                await asyncio.to_thread(self._archive.remove, root)
                raise
            self._serial += 1
            self.current = Current(name=name, folder=made["folder"], root=root, serial=self._serial)
            await self._rescope()
            self.ws.audit.write(who, "new_sab_project", None, name=name)
        await self._changed()

    # ===== open =====

    async def open(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Open a project: {"path": a .sab (or a project's folder), "discard"?, "ask"?}. With unsaved
        work open it asks first: Conflict, or (ask: another program asked, a double-click) the page asks
        the user. {"cancel": true}: that question goes."""
        body = body if isinstance(body, dict) else {}
        if body.get("cancel") is True:
            self._asked = None
            await self._changed()
            return self.state()
        path = body.get("path")
        if not isinstance(path, str) or not path.strip():
            raise ValueError('Send {"path": "the project\'s .sab file"}.')
        try:
            full = self._archive.full(path.strip())
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        if body.get("ask") is True and body.get("discard") is not True and self.dirty():
            self._asked = full
            await self._changed()
            return self.state() | {"asked": full, "page": self.ws.live.page_open()}
        async with self._busy:
            self._check_discard(body)
            if self._archive.is_folder(full):
                return await self._adopt(full, who, clear=True)
            try:
                text = await asyncio.to_thread(self._archive.manifest, full)
            except FileNotFoundError as error:
                raise NotFound(str(error)) from None
            manifest, read_only = rules.read_manifest(text)
            await self._clear(who)
            self._asked = None
            root, folder, found = await asyncio.to_thread(
                self._archive.unpack, full, manifest.special(), manifest.name
            )
            self._serial += 1
            self.current = Current(
                name=rules.name_of_file(full),
                folder=folder,
                path=full,
                root=root,
                read_only=read_only,
                manifest=manifest,
                keep_rows={t.name: True for t in manifest.tables if t.source.needs_rows and t.source.rows},
                layout={
                    "workbench": dict(manifest.workbench),
                    "home": dict(manifest.tabs),
                    "diagram": dict(manifest.diagram),
                },
                serial=self._serial,
                autosave=manifest.autosave,
            )
            # An older project's own connections: into the library, before its tables are read from them.
            await self._library_from(folder, self.current.name)
            await self._rescope()
            sab_folder = self._archive.folder_of(full)
            ordered = sorted(
                manifest.tables, key=lambda t: t.source.kind == "query"
            )  # queries read the others
            for table in ordered:
                await self._load(table, sab_folder, found, who)
            if manifest.visualizations and manifest.visualizations in found:
                try:
                    saved = json.loads(
                        await asyncio.to_thread(self._archive.read_text, found[manifest.visualizations])
                    )
                    cards = saved["versions"][-1]["cards"] if isinstance(saved, dict) else []
                except (ValueError, KeyError, IndexError, TypeError):
                    cards = []
                await self._cards.restore(cards, who)
            if manifest.model and manifest.model in found:
                try:
                    await self._models.replace(
                        read_tang(await asyncio.to_thread(self._archive.read_text, found[manifest.model]))
                    )
                except TangError:
                    pass  # a model edited into something else: the project opens without it
            for opened in self.opened:
                await opened(folder, manifest.extra)
            self._recent.add(full, self._now())
            self.current.saved_key = self._key()
            self.ws.audit.write(who, "open_sab_project", None, tables=len(manifest.tables))
        await self._changed()
        return self.state() | {"page": self.ws.live.page_open()}

    async def _adopt(self, folder: str, who: str, clear: bool) -> dict[str, Any]:
        """A folder project (today's: a folder with data.ipynb) as the open project: its own working
        folder. Saved as a .sab with Save as."""
        if clear:
            await self._clear(who)
        listed = self._projects.open({"folder": folder}, who)
        self._serial += 1
        self.current = Current(name=str(listed["name"]), folder=str(listed["folder"]), serial=self._serial)
        await self._library_from(self.current.folder, self.current.name)
        await self._rescope()
        self.current.saved_key = self._key()
        await self._changed()
        return self.state()

    async def _load(self, table: TableEntry, sab_folder: str | None, found: dict[str, str], who: str) -> None:
        """Read one table again from where it came from, as grids with its steps; or say why not."""
        current = self._need()
        current.waiting.pop(table.name, None)
        current.problems.pop(table.name, None)
        source = table.source
        problem: str | None = None
        try:
            if source.kind == "connection":
                problem = await self._from_connection(table, who)
            elif source.kind == "file":
                there = next(
                    (p for p in rules.candidates(source, sab_folder) if self._archive.exists(p)), None
                )
                if there is None:
                    problem = "no_file"
                else:
                    await self._datasets.load_file(table.name, there, source.sheet, True, who)
            elif source.kind == "query" and source.sql:
                await self._datasets.build_from_query(table.name, source.sql, False, who)
            elif source.kind == "cell":
                problem = "not_run"  # nothing runs code on open: the user runs the notebook
            elif table.rows_file and table.rows_file in found:
                rows = await asyncio.to_thread(self._archive.read_rows, found[table.rows_file])
                origin = Origin("paste")
                await self._datasets.store_table(table.name, rows, "arrow", True, who, origin=origin)
            else:
                problem = "no_rows"
        except (Conflict, NotFound, Refused, ValueError, OSError, KeyError) as error:
            problem = str(error).strip("'\"") or type(error).__name__
        except Exception as error:  # a connection's own code failing: its words, never a dead end
            problem = str(error)[:300] or type(error).__name__
        if problem is not None:
            current.waiting[table.name] = table
            current.problems[table.name] = rules.fix_for(table.name, source, problem)
            return
        await self._apply(table)

    async def _from_connection(self, table: TableEntry, who: str) -> str | None:
        source = table.source
        name = source.connection or ""
        listed = {
            str(c["name"]).casefold(): str(c["name"]) for c in self._connections.listing()["connections"]
        }
        if name.casefold() not in listed:
            return "no_connection"
        if self._connections.needs_passwords(listed[name.casefold()]):
            return "needs_password"
        if source.sql and not source.table:
            # A query of the user's on the connection (its table's connection was swapped): run again.
            read = await self._connections.read_query(
                listed[name.casefold()], source.sql, {"dataset": source.schema} if source.dax else {}
            )
            origin = Origin("connection", connection=read.connection, sql=source.sql, dax=read.dax)
            await self._datasets.store_table(table.name, read.table, "connection", True, who, origin=origin)
            return None
        place = {"database": source.database, "schema": source.schema, "table": source.table}
        answer = await self._connections.open_table(
            listed[name.casefold()], place | {"all": source.whole}, who
        )
        if "sheets" in answer:
            return f"{source.table or name} has several sheets: open it from the connection."
        dataset = str(answer.get("dataset") or "")
        if dataset and dataset != table.name and self.ws.store.get(table.name) is None:
            await self._datasets.rename(dataset, table.name, who)
        return None

    async def _apply(self, table: TableEntry) -> None:
        """A table that came back: its grids' steps as they were (no undo entry: this is where it starts)."""
        grids = self.ws.grids.for_dataset(table.name)
        for index, entry in enumerate(table.grids):
            made = index >= len(grids)
            grid = self.ws.grids.create(table.name) if made else grids[index]
            try:
                grid.steps = steps_from_json(list(entry.steps))
                grid.settings = ViewSettings.from_json(dict(entry.settings) or None)
            except ValueError:
                pass  # a step this version does not know: the grid opens without its steps
            if made:
                await self.ws.live.broadcast({"type": "grid_shown", "grid": grid.id, "dataset": table.name})
            else:
                await self.ws.live.broadcast(
                    {"type": "grid_updated", "grid": grid.id, "by": "user", "gen": grid.gen}
                )

    async def _arrived(self, name: str, grid_id: str) -> None:
        """A table arrived by any way (its notebook ran, a paste): its steps waiting in the project apply."""
        current = self.current
        if current is None or name not in current.waiting or self._busy.locked():
            return
        table = current.waiting.pop(name)
        current.problems.pop(name, None)
        grid = self.ws.grids.get(grid_id)
        if grid is not None and not grid.steps:
            await self._apply(table)
        await self._changed()

    async def fix(self, body: Any, who: str = "user") -> dict[str, Any]:
        """A table that did not come back: {"table", "path"?: where its file is now, "remove"?: true}.
        Without either, it is tried again (a connection added since, its notebook run)."""
        current = self._need()
        if not isinstance(body, dict) or not isinstance(body.get("table"), str):
            raise ValueError('Send {"table": its name, "path"?: its file now, "remove"?: true}.')
        name = body["table"]
        table = current.waiting.get(name)
        if table is None:
            raise NotFound(f"{name} is not waiting to come back.")
        if body.get("remove") is True:
            current.waiting.pop(name)
            current.problems.pop(name, None)
            await self._changed()
            return self.state()
        path = body.get("path")
        if isinstance(path, str) and path.strip():
            if table.source.kind != "file":
                raise ValueError(f"{name} does not come from a file.")
            full = self._full(path)
            table = replace(table, source=replace(table.source, path=full, absolute=full))
        async with self._busy:
            sab_folder = self._archive.folder_of(current.path) if current.path else None
            await self._load(table, sab_folder, {}, who)
        await self._changed()
        return self.state()

    # ===== a table's connection swapped (services/connection_swap.py) =====

    def waiting(self, name: str) -> TableEntry | None:
        """A table of the open project that has not come back, as the file says it (None: not waiting)."""
        return self.current.waiting.get(name) if self.current is not None else None

    def waiting_tables(self) -> list[TableEntry]:
        return list(self.current.waiting.values()) if self.current is not None else []

    async def move_waiting(self, name: str, source: Source, who: str) -> dict[str, Any] | None:
        """A waiting table read again from another source (its steps as they were): None when it came
        back, else its problem as the strip shows it."""
        current = self._need()
        table = current.waiting.get(name)
        if table is None:
            raise NotFound(f"{name} is not waiting to come back.")
        async with self._busy:
            sab_folder = self._archive.folder_of(current.path) if current.path else None
            await self._load(replace(table, source=source), sab_folder, {}, who)
        await self._changed()
        return current.problems.get(name)

    async def wait_again(self, table: TableEntry, problem: dict[str, Any] | None) -> None:
        """A table back to waiting as it was (a swap undone): its source, steps and problem."""
        current = self._need()
        current.waiting[table.name] = table
        if problem is not None:
            current.problems[table.name] = problem
        await self._changed()

    async def changed(self) -> None:
        """Something the project is made of changed elsewhere (a table's source): the pages hear it."""
        await self._changed()

    # ===== save =====

    async def save(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Save: {"keep_rows"?: {"pasted_1": true}, "path"?}. The first save of a project made here
        names where it goes (path); without a project open, the open work becomes one there."""
        body = body if isinstance(body, dict) else {}
        keep = _keep_rows(body.get("keep_rows"))
        path = body.get("path")
        if path is not None and (not isinstance(path, str) or not path.strip()):
            raise ValueError("path is where the .sab goes.")
        folder = body.get("folder")
        if (
            isinstance(folder, str)
            and folder.strip()
            and (self.current is None or self.current.folder != folder)
        ):
            await self._adopt(self._full(folder), who, clear=False)
        if self.current is None:
            if not path:
                raise NotFound(
                    'No project is open: send {"path": where its .sab goes} to save the open work as one.'
                )
            await self._make(
                rules.check_name(rules.name_of_file(rules.with_suffix(path.strip()))), False, who
            )
        current = self._need()
        if current.read_only:
            raise Refused(current.read_only)
        target = rules.with_suffix(path.strip()) if isinstance(path, str) and path.strip() else current.path
        if target is None:
            raise Conflict('This project has not been saved yet: send {"path": where its .sab goes}.')
        try:
            target = self._archive.full(target)
        except FileNotFoundError as error:
            raise NotFound(str(error)) from None
        current.keep_rows |= keep
        notes: list[str] = []
        if self._ask_workbench is not None and self.ws.live.workbench_open():
            # The Workbench's unsaved documents of this project are saved first, as they stand there.
            try:
                await asyncio.wait_for(
                    self._ask_workbench("project.saveDocuments", {"folder": current.folder}),
                    WORKBENCH_SAVE_SECONDS,
                )
            except Exception:  # a window that does not answer: the files as they are
                if current.unsaved:
                    notes.append(f"Saved as on disk: {', '.join(current.unsaved)} had unsaved changes there.")
        async with self._busy:
            tables = self._tables()
            rows_tables = [t.name for t in tables if t.source.needs_rows and current.keep_rows.get(t.name)]
            cards, card_rows = self._cards.snapshot()
            if who == "agent" and (rows_tables or card_rows):
                detail = "\n".join(
                    [
                        "Save the project, with these rows kept in the file:",
                        f"  {target}",
                        *(f"  {name} ({self._rows(name):,} rows)" for name in rows_tables),
                        *(["  Visualizations' table cards"] if card_rows else []),
                    ]
                )
                if not await self._approvals.ask(current.name, "save the project with rows", detail):
                    raise Refused("The user declined (or did not answer): the project was not saved.")
            written = await self._write(current, target, rows_tables, cards)
            current.path = written
            current.name = rules.name_of_file(written)
            current.saved_key = self._key()
            current.unsaved = []
            self._recent.add(written, self._now())
            self.ws.audit.write(who, "save_sab_project", None, tables=len(tables), rows=len(rows_tables))
        await self._changed()
        return self.state() | {"saved": written, "rows": rows_tables, "notes": notes}

    def _rows(self, name: str) -> int:
        info = self.ws.store.get(name)
        return info.row_count if info else 0

    async def _write(self, current: Current, target: str, rows_tables: list[str], cards: list[Any]) -> str:
        """The .sab at `target`: the manifest, the project's files, Visualizations, the model, ticked rows."""
        before = current.path
        current.path = target  # the sources are written relative to where the file goes
        try:
            tables = self._tables()
        finally:
            current.path = before
        files = await asyncio.to_thread(self._archive.files, current.folder)
        files += await asyncio.to_thread(self._archive.app_files, current.folder)  # saved dashboards
        entries: list[tuple[str, bytes | str]] = []
        for relative, _, _ in files:
            raw = await asyncio.to_thread(self._archive.read_file, current.folder, relative)
            if relative.lower().endswith((".ipynb", ".py")):
                try:
                    raw = rules.for_the_file(relative, raw.decode("utf-8-sig")).encode("utf-8")
                except (UnicodeDecodeError, ValueError):
                    pass  # not one this version reads: as it is
            entries.append((relative, raw))
        taken = [relative for relative, _, _ in files]
        scratch = await asyncio.to_thread(self._archive.scratch)
        try:
            written: list[TableEntry] = []
            for table in tables:
                table = rules.carried(current.manifest, table.name, table)
                if table.name in rows_tables and self.ws.store.get(table.name) is not None:
                    entry = rules.rows_entry(table.name, taken)
                    taken.append(entry)
                    rows = await self._rows_of(table.name)
                    entries.append((entry, await asyncio.to_thread(self._archive.write_rows, scratch, rows)))
                    table = replace(table, rows_file=entry, source=replace(table.source, rows=True))
                written.append(table)
            cards_entry = rules.VISUALIZATIONS if [c for c in cards if c.get("kind") != "theme"] else None
            if cards_entry:
                body = {
                    "name": current.name,
                    "versions": [{"saved": _now_text(self._now()), "cards": cards}],
                }
                entries.append((cards_entry, json.dumps(body, default=str).encode("utf-8")))
            model = self._models.model
            model_entry = rules.MODEL if model.tables() or model.relationships else None
            if model_entry:
                entries.append((model_entry, write_tang(model).encode("utf-8")))
            layout = current.layout
            earlier = current.manifest
            manifest = Manifest(
                name=current.name if before == target else rules.name_of_file(target),
                tables=tuple(written),
                app_version=self._version,
                saved=_now_text(self._now()),
                tabs=layout.get("home") or {},
                workbench=layout.get("workbench") or {},
                diagram=layout.get("diagram") or {},
                visualizations=cards_entry,
                model=model_entry,
                autosave=current.autosave,
                extra=(dict(earlier.extra) if earlier else {}) | _extras(self.manifest_extras),
            )
            entries.insert(0, (rules.MANIFEST, rules.write_manifest(manifest).encode("utf-8")))
            try:
                done = await asyncio.to_thread(self._archive.write, target, entries)
            except FileNotFoundError as error:
                raise NotFound(str(error)) from None
            except PermissionError as error:
                raise Conflict(str(error)) from None
            current.manifest = manifest
            return done
        finally:
            await asyncio.to_thread(self._archive.remove, scratch)

    async def _rows_of(self, name: str) -> Any:
        info = self.ws.store.get(name)
        if info is None:
            raise NotFound(f"{name} is not open.")
        return await self.ws.workers.run(
            BACKGROUND,
            self._reader.query_table,
            self.ws.store.cursor(),
            f"SELECT * FROM {info.table}",  # noqa: S608 (a quoted dataset name)
        )

    # ===== close, the layout, the recent list =====

    async def close(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Close the project: {"discard"?}. Asks first (Conflict) when it has unsaved changes."""
        body = body if isinstance(body, dict) else {}
        self._need()
        async with self._busy:
            self._check_discard(body)
            await self._clear(who)
            self._serial += 1
            self.ws.audit.write(who, "close_sab_project", None)
        await self._changed()
        return self.state()

    async def layout(self, body: Any) -> dict[str, Any]:
        """A window's layout, kept for the next save: {"window": "workbench" | "home" | "diagram",
        "layout": {...}, "unsaved"?: the Workbench's documents with unsaved changes}."""
        if not isinstance(body, dict) or body.get("window") not in ("workbench", "home", "diagram"):
            raise ValueError('Send {"window": "workbench", "home" or "diagram", "layout": {...}}.')
        current = self.current
        if current is None:
            return {"kept": False}
        layout = body.get("layout")
        if isinstance(layout, dict):
            if len(json.dumps(layout, default=str)) > MAX_LAYOUT_CHARS:
                raise ValueError("That layout is too large to keep.")
            current.layout[str(body["window"])] = layout
        unsaved = body.get("unsaved")
        if body["window"] == "workbench" and isinstance(unsaved, list):
            now = [str(u)[:200] for u in unsaved[:200] if isinstance(u, str)]
            if now != current.unsaved:
                current.unsaved = now
                await self._changed()
        return {"kept": True}

    # ===== autosave =====

    async def set_autosave(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Autosave on or off: {"on": true}. Kept in the project's file at once (its project.json only:
        nothing else is saved by the switch)."""
        if not isinstance(body, dict) or not isinstance(body.get("on"), bool):
            raise ValueError('Send {"on": true} or {"on": false}.')
        current = self._need()
        if current.read_only:
            raise Refused(current.read_only)
        current.autosave = body["on"]
        current.autosave_error = None
        self._settling = None
        if current.path is not None and current.manifest is not None:
            manifest = replace(current.manifest, autosave=current.autosave)
            try:
                await asyncio.to_thread(
                    self._archive.replace_manifest, current.path, rules.write_manifest(manifest)
                )
            except (OSError, rules.SabError) as error:
                raise Conflict(f"The switch could not be kept in {current.path}: {error}") from None
            current.manifest = manifest
        self.ws.audit.write(who, "project_autosave", None, on=current.autosave)
        await self._changed()
        return self.state()

    async def autosave_tick(self) -> bool:
        """One look: with autosave on and changes that have settled since the last look, a quiet save.
        True when it saved."""
        current = self.current
        if (
            current is None
            or not current.autosave
            or current.path is None
            or current.read_only
            or self._busy.locked()
            or not self.dirty()
        ):
            self._settling = None
            return False
        seen = json.dumps([self._key(), current.unsaved])
        if seen != self._settling:
            self._settling = seen  # still changing: the next look saves, if it stays so
            return False
        self._settling = None
        try:
            await self.save({}, AUTOSAVE)
        except Exception as error:  # said in the project's state; the next change tries again
            if self.current is current:
                current.autosave_error = str(error)[:300] or type(error).__name__
                await self._changed()
            return False
        current.autosave_error = None
        return True

    async def run_autosave(self) -> None:
        """The server's autosave: a look every couple of seconds while it runs."""
        while True:
            await asyncio.sleep(self._autosave_seconds)
            try:
                await self.autosave_tick()
            except Exception:  # noqa: S112 (a look that failed: the next one tries again)
                continue

    def recent(self) -> dict[str, Any]:
        return {"recent": self._recent.all()}

    async def forget(self, body: Any) -> dict[str, Any]:
        """Remove from the list: {"path"}."""
        if not isinstance(body, dict) or not isinstance(body.get("path"), str):
            raise ValueError('Send {"path": the project\'s file}.')
        if not self._recent.remove(body["path"]):
            raise NotFound("That project is not in the list.")
        await self._changed()
        return self.recent()

    async def stop(self) -> None:
        """The server stops: the temporary working folder goes."""
        if self.current is not None:
            self._archive.remove(self.current.root)


def _extras(makers: list[Callable[[], dict[str, Any]]]) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for make in makers:
        found |= make()
    return found
