"""A project is a folder (the owner, 2026-11-17: "I think we need to just consider entire folders projects
and take out the .sab" / "that way we can share entire projects in git repos nativly"; rules in
domain/sab_files.py). For the home page, the Workbench window and the agent alike.

  new       a project of its own in a new or empty folder (by default in the projects folder, named for
            the project): its scaffold (services/projects.py: data.ipynb with the tables open now, data.py,
            the type's own files), .gitignore and README.md, then .sab/ written and the project opened
  open      a folder: its .sab/project.json read; each table read again from where it came from, as a
            grid with its steps; Visualizations, the relationships and the windows' layout as they were.
            A table that cannot come back says so, with the click that fixes it (fix). A folder with the
            scaffold but no .sab/ opens as a project with no tables yet; any other folder is not opened but
            answered `not_a_project`, and `make: true` scaffolds it around what is there (never writing
            over a file)
  save      .sab/ written from the open tables, Visualizations and the model, each file only when its bytes
            change. The documents are saved by their own Save. A pasted or pushed table's rows go into
            .sab/data/ only when ticked (keep_rows); the agent's save waits for the user's Allow when it
            would keep rows. Never a password
  autosave  on by default (the user's switch, kept in .sab/project.json): .sab/ kept current once a change
            settles, quietly
  copy      Copy project to: the folder copied elsewhere (saved first; .sab/data/ only on a tick, and the
            agent's with rows waits for the user's Allow)
  close     the tables, Visualizations and the model closed
  scope     the open project's saved dashboards are its own (.sab/visualizations/): each open, new and
            close tells the stores (scope). Connections, APIs, vaults, blades and variables are the
            library's: an older project's own .sab/blades go into the library as it opens (adopt)
  recent    the projects opened, by folder (recent_projects.json)

Whether there are unsaved changes is worked out, not tracked: what a save would write (the tables, their
sources and steps, Visualizations, the model) against what the last save or open wrote, and the
Workbench's own unsaved documents. Opening another project when that would lose work asks first
(Conflict), and only then. One project is open at a time (memory only).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from swissarmybench.domain import notebooks
from swissarmybench.domain import sab_files as rules
from swissarmybench.domain.projects import DATA_NOTEBOOK, check_folder_name
from swissarmybench.domain.relationships import Model, RelationshipSetError, read_set, write_set
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
    """A project's folder on disk (adapters/sab_files.py)."""

    def full(self, path: str) -> str: ...

    def join(self, folder: str, name: str) -> str: ...

    def exists(self, path: str) -> bool: ...

    def folder_of(self, path: str) -> str: ...

    def is_folder(self, path: str) -> bool: ...

    def read_state(self, folder: str, relative: str) -> bytes | None: ...

    def write_state(self, folder: str, relative: str, body: bytes) -> bool: ...

    def remove_state(self, folder: str, relative: str) -> bool: ...

    def rows_bytes(self, table: Any) -> bytes: ...

    def read_rows(self, path: str) -> Any: ...

    def move_old_dashboards(self, folder: str) -> bool: ...

    def ensure_ignored(self, folder: str, name: str) -> list[str]: ...

    def top_names(self, folder: str) -> list[str]: ...

    def empty_folder(self, path: str) -> str: ...

    def copy_project(self, source: str, target: str, data: bool) -> str: ...


class Recent(Protocol):
    def all(self) -> list[dict[str, Any]]: ...

    def add(self, path: str, when: float) -> None: ...

    def remove(self, path: str) -> bool: ...


@dataclass
class Current:
    """The open project: its folder is the project."""

    name: str
    folder: str
    read_only: str | None = None  # why it cannot be saved here (a newer format)
    manifest: Manifest | None = None  # as last read or written: what this version does not know is kept
    keep_rows: dict[str, bool] = field(default_factory=dict)
    saved_key: str | None = None
    layout: dict[str, Any] = field(default_factory=dict)  # each window's: workbench, home, diagram
    unsaved: list[str] = field(default_factory=list)  # the Workbench's documents with unsaved changes
    problems: dict[str, dict[str, Any]] = field(default_factory=dict)  # tables not back, and their fix
    autosave: bool = True
    autosave_error: str | None = None  # the last quiet save that failed, in words
    waiting: dict[str, TableEntry] = field(default_factory=dict)  # their steps, for when they arrive
    serial: int = 0

    @property
    def path(self) -> str:
        return self.folder


def _keep_rows(raw: Any) -> dict[str, bool]:
    if raw is None:
        return {}
    if not isinstance(raw, dict) or not all(
        isinstance(k, str) and isinstance(v, bool) for k, v in raw.items()
    ):
        raise ValueError('keep_rows is {"table": true or false}: keep its rows in the project.')
    return dict(raw)


def _base(path: str) -> str:
    return path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


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
        projects_folder: Callable[[], str] | None = None,
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
        # The stores that follow the open project (its saved dashboards): its folder, or None.
        self._scope = scope
        # An older project's own connections and blades (.sab/blades) moved into the library (folder, name).
        self._adopt_blades = adopt
        self._autosave_seconds = autosave_seconds
        # Where a new project's folder goes when none is named (the Project Explorer's projects folder).
        self._projects_folder = projects_folder
        self._settling: str | None = None  # autosave: what a save would write, as last seen
        self.current: Current | None = None
        self._serial = 0
        self._asked: str | None = None  # a project another program asked to open (the page asks the user)
        self._busy = asyncio.Lock()
        datasets.stored.append(self._arrived)
        # What other features keep in project.json (Structures: the ones open), and what they do once a
        # project has opened (its open structures come back): each a key of the manifest's own.
        self.manifest_extras: list[Callable[[], dict[str, Any]]] = []
        self.opened: list[Callable[[str, Mapping[str, Any]], Awaitable[None]]] = []
        self.on_opened: list[Callable[[str], None]] = []  # the Project Explorer's "last opened"

    # ===== what is open, and whether a save would change anything =====

    def _source(self, name: str, keep: bool) -> Source:
        current = self.current
        origin = self._datasets.origins.get(name)
        folder = current.folder if current else None
        return rules.source_of(
            origin, folder, folder, self._kernel_document(origin.kernel), origin.place, origin.whole, keep
        )

    def _tables(self) -> list[TableEntry]:
        """The open tables as the project says them (and the ones waiting to come back, as they were)."""
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
        """What a save would write now, as text (the windows' layout aside: moving a tab is no change)."""
        current = self.current
        tables = [t.to_json() for t in self._tables()]
        model = self._models.model.to_json() if self._models.model.tables() else None
        keep = sorted(k for k, v in (current.keep_rows if current else {}).items() if v)
        return json.dumps([tables, self._cards.state_key(), model, keep], default=str, sort_keys=True)

    def _has_work(self) -> bool:
        return bool(self.ws.store.all()) or self._cards.holds_cards or bool(self._models.model.tables())

    def dirty(self) -> bool:
        """Would something be lost if the project (or the loose work, with none open) closed now?"""
        current = self.current
        if current is None:
            return self._has_work()
        if current.unsaved:
            return True
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
                "path": current.folder,
                "folder": current.folder,
                "type": self._projects.type_of(current.folder),
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
            # The open work with no project: what making it one would keep (its rows' ticks).
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

    def projects_folder(self) -> str | None:
        return self._projects_folder() if self._projects_folder is not None else None

    # ===== clearing the workspace =====

    async def _clear(self, who: str) -> None:
        """Every table closed, Visualizations and the model emptied."""
        for info in list(self.ws.store.all()):
            await self._datasets.close(info.name, who)
        await self._cards.clear()
        if self._models.model.tables() or self._models.model.relationships:
            await self._models.replace(Model())
        self.current = None
        self._projects.opened = None
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

    def _remember(self, folder: str) -> None:
        self._recent.add(folder, self._now())
        for hook in self.on_opened:
            hook(folder)

    # ===== new =====

    def _target(self, body: dict[str, Any]) -> str:
        """A new project's folder: {"path": the folder itself} or {"name", "folder"?: where it goes (the
        projects folder by default)}."""
        path = body.get("path")
        if isinstance(path, str) and path.strip():
            if path.strip().lower().endswith(".sab"):  # the single-file project of 0.0.17
                raise ValueError("A project is a folder: name a folder, not a .sab file.")
            return self._full(path)
        name = body.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError('Send {"name": the project\'s name, "folder"?: where its folder goes}.')
        name = check_folder_name(name)
        parent = body.get("folder")
        if not isinstance(parent, str) or not parent.strip():
            parent = self.projects_folder()
            if not parent:
                raise ValueError('Send {"folder": where the project\'s folder goes}.')
        return self._full(self._archive.join(parent.strip(), name))

    async def new(self, body: Any, who: str = "user") -> dict[str, Any]:
        """New project: {"name", "folder"?: where its folder goes, or "path": a new or empty folder,
        "type"?, "app"?, "notebooks"?, "autosave"? (on unless false), "discard"?}. The folder is
        scaffolded and the project opened, its .sab/ written at once. The tables open now (with no
        project) go into it: its data.ipynb starts with them."""
        body = body if isinstance(body, dict) else {}
        target = self._target(body)
        name = check_folder_name(_base(target))
        if self.current is not None:
            self._check_discard(body)
        try:
            await asyncio.to_thread(self._archive.empty_folder, target)
        except FileExistsError as error:
            raise Conflict(str(error)) from None
        except OSError as error:
            raise NotFound(f"{target} cannot be made here ({error}).") from None
        kind = body.get("type")
        app = body.get("app")
        if app is None:  # a Streamlit project has its app's canvas; the others start with notebooks
            app = kind == "streamlit"
        listing: dict[str, Any] = {}
        async with self._busy:
            if self.current is not None:
                await self._clear(who)
            listing = await self._projects.create(
                {"folder": self._archive.folder_of(target), "name": name, "app": app is True, "type": kind}
                | ({"notebooks": body["notebooks"]} if body.get("notebooks") is not None else {}),
                who,
                remember=False,
                rows=False,
            )
            await asyncio.to_thread(self._archive.ensure_ignored, target, name)
            self._serial += 1
            self.current = Current(
                name=name, folder=target, serial=self._serial, autosave=body.get("autosave") is not False
            )
            self._projects.opened = target
            await self._rescope()
            self._remember(target)
            self.ws.audit.write(who, "new_project_folder", target, type=self._projects.type_of(target))
        try:
            saved = await self.save({}, who)
        except BaseException:
            async with self._busy:
                await self._clear(who)
            await self._changed()
            raise
        return saved | {k: listing[k] for k in ("folder", "name", "data", "files", "type") if k in listing}

    # ===== open =====

    async def open(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Open a project: {"path": its folder, "make"?, "discard"?, "ask"?}. With unsaved work open it
        asks first: Conflict, or (ask: another program asked) the page asks the user. {"cancel": true}:
        that question goes. A folder that is not a project is answered `not_a_project` (make: true
        makes it one around what is there)."""
        body = body if isinstance(body, dict) else {}
        if body.get("cancel") is True:
            self._asked = None
            await self._changed()
            return self.state()
        path = body.get("path") or body.get("folder")
        if not isinstance(path, str) or not path.strip():
            raise ValueError('Send {"path": the project\'s folder}.')
        full = self._full(path)
        if not self._archive.is_folder(full):
            if self._archive.exists(full):
                raise ValueError(f"{full} is a file: open a project's folder.")
            raise NotFound(f"{full} is not a folder.")
        names = await asyncio.to_thread(self._archive.top_names, full)
        if not rules.is_project(names) and body.get("make") is not True:
            return self.state() | {"not_a_project": full}
        if body.get("ask") is True and body.get("discard") is not True and self.dirty():
            self._asked = full
            await self._changed()
            return self.state() | {"asked": full, "page": self.ws.live.page_open()}
        # A folder never opened as a project (no .sab/ yet: made with the scaffold alone, or a plain one made
        # a project now) takes the open tables with no project into it: nothing is lost, nothing asked.
        adopt = rules.MANIFEST_PATH not in names and self.current is None
        async with self._busy:
            if not adopt:
                self._check_discard(body)
            made: list[str] = []
            if not rules.is_project(names):
                made = await asyncio.to_thread(self._make_around, full)
            await self._open_folder(full, who, keep_work=adopt)
            self.ws.audit.write(who, "open_project_folder", full, made=len(made))
        await self._changed()
        return self.state() | {"page": self.ws.live.page_open(), "made": made}

    def _make_around(self, folder: str) -> list[str]:
        """A folder made a project around what is there: an empty data.ipynb, .gitignore and README.md
        when it has none, .sab/ (the files written; nothing that was there is written over)."""
        made: list[str] = []
        if self._archive.read_state(folder, DATA_NOTEBOOK) is None:
            self._archive.write_state(folder, DATA_NOTEBOOK, notebooks.write_notebook([]).encode("utf-8"))
            made.append(DATA_NOTEBOOK)
        made += self._archive.ensure_ignored(folder, _base(folder))
        manifest = Manifest(name=_base(folder), app_version=self._version, autosave=True)
        self._archive.write_state(folder, rules.MANIFEST_PATH, rules.write_manifest(manifest).encode("utf-8"))
        return [*made, rules.MANIFEST_PATH]

    async def _open_folder(self, folder: str, who: str, keep_work: bool = False) -> None:
        """The project in `folder` as the open one: its tables read again, Visualizations, the model.
        `keep_work`: the open tables, Visualizations and model (no project open) become its own."""
        raw = await asyncio.to_thread(self._archive.read_state, folder, rules.MANIFEST_PATH)
        try:
            manifest, read_only = (
                rules.read_manifest(raw.decode("utf-8-sig"), folder=True)
                if raw is not None
                else (Manifest(name=_base(folder), autosave=True), None)
            )
        except (UnicodeDecodeError, rules.SabError) as error:
            raise ValueError(f"{folder}: {error}") from None
        if not keep_work:
            await self._clear(who)
        self._asked = None
        await asyncio.to_thread(self._archive.move_old_dashboards, folder)
        self._serial += 1
        self.current = Current(
            name=_base(folder),
            folder=folder,
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
        self._projects.opened = folder
        # An older project's own connections: into the library, before its tables are read from them.
        await self._library_from(folder, self.current.name)
        await self._rescope()
        ordered = sorted(manifest.tables, key=lambda t: t.source.kind == "query")  # queries read the others
        for table in ordered:
            await self._load(table, who)
        cards_text = await self._state_text(folder, manifest.visualizations)
        if cards_text is not None:
            try:
                saved = json.loads(cards_text)
                cards = saved["versions"][-1]["cards"] if isinstance(saved, dict) else []
            except (ValueError, KeyError, IndexError, TypeError):
                cards = []
            await self._cards.restore(cards, who)
        model_text = await self._state_text(folder, manifest.model)
        if model_text is not None:
            try:
                await self._models.replace(read_set(model_text))
            except RelationshipSetError:
                pass  # a model edited into something else: the project opens without it
        for opened in self.opened:
            await opened(folder, manifest.extra)
        self._remember(folder)
        # Taken in, the open work is not saved here yet (Save or Autosave writes it).
        self.current.saved_key = None if keep_work and self._has_work() else self._key()

    async def _state_text(self, folder: str, relative: str | None) -> str | None:
        if not relative:
            return None
        try:
            raw = await asyncio.to_thread(self._archive.read_state, folder, relative)
        except (OSError, rules.SabError):
            return None
        return raw.decode("utf-8-sig", "replace") if raw is not None else None

    async def _load(self, table: TableEntry, who: str) -> None:
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
                    (p for p in rules.candidates(source, current.folder) if self._archive.exists(p)), None
                )
                if there is None:
                    problem = "no_file"
                else:
                    await self._datasets.load_file(table.name, there, source.sheet, True, who)
            elif source.kind == "query" and source.sql:
                await self._datasets.build_from_query(table.name, source.sql, False, who)
            elif source.kind == "cell":
                problem = "not_run"  # nothing runs code on open: the user runs the notebook
            elif table.rows_file and self._archive.exists(rules_path(current.folder, table.rows_file)):
                rows = await asyncio.to_thread(
                    self._archive.read_rows, rules_path(current.folder, table.rows_file)
                )
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
            await self._load(table, who)
        await self._changed()
        return self.state()

    # ===== a table's connection swapped (services/connection_swap.py) =====

    def waiting(self, name: str) -> TableEntry | None:
        """A table of the open project that has not come back, as the project says it (None: not waiting)."""
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
            await self._load(replace(table, source=source), who)
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
        """Save: {"keep_rows"?: {"pasted_1": true}}: the project's .sab/ written, each file only when its
        bytes change (the documents are saved by their own Save; the Workbench's are saved first). With
        no project open, {"path": a new or empty folder} makes the open work a project there."""
        body = body if isinstance(body, dict) else {}
        keep = _keep_rows(body.get("keep_rows"))
        if self.current is None:
            if not body.get("path") and not body.get("name"):
                raise NotFound(
                    'No project is open: send {"path": a new or empty folder} to make the open work one.'
                )
            made = await self.new(
                {k: body[k] for k in ("path", "name", "folder", "type", "autosave") if k in body}, who
            )
            return (await self.save({"keep_rows": keep}, who) if keep else made) | {
                k: made[k] for k in ("folder", "name", "data", "files", "type") if k in made
            }
        if isinstance(body.get("path"), str) and body["path"].strip():
            raise ValueError("A project is its folder: Copy project to… (project_copy) makes another.")
        current = self._need()
        if current.read_only:
            raise Refused(current.read_only)
        current.keep_rows |= keep
        notes: list[str] = []
        if who != AUTOSAVE and self._ask_workbench is not None and self.ws.live.workbench_open():
            # The Workbench's unsaved documents of this project are saved first, as they stand there.
            try:
                await asyncio.wait_for(
                    self._ask_workbench("project.saveDocuments", {"folder": current.folder}),
                    WORKBENCH_SAVE_SECONDS,
                )
            except Exception:  # a window that does not answer: the files as they are
                if current.unsaved:
                    notes.append(f"{', '.join(current.unsaved)} had unsaved changes in the Workbench.")
        async with self._busy:
            tables = self._tables()
            rows_tables = [t.name for t in tables if t.source.needs_rows and current.keep_rows.get(t.name)]
            cards, card_rows = self._cards.snapshot()
            if who == "agent" and (rows_tables or card_rows):
                detail = "\n".join(
                    [
                        "Save the project, with these rows kept in its folder:",
                        f"  {current.folder}",
                        *(f"  {name} ({self._rows(name):,} rows)" for name in rows_tables),
                        *(["  Visualizations' table cards"] if card_rows else []),
                    ]
                )
                if not await self._approvals.ask(current.name, "save the project with rows", detail):
                    raise Refused("The user declined (or did not answer): the project was not saved.")
            written = await self._write(current, rows_tables, cards)
            current.saved_key = self._key()
            current.unsaved = []
            if who != AUTOSAVE:
                self.ws.audit.write(who, "save_project", None, tables=len(tables), rows=len(rows_tables))
        await self._changed()
        return self.state() | {
            "saved": current.folder,
            "written": written,
            "rows": rows_tables,
            "notes": notes,
        }

    def _rows(self, name: str) -> int:
        info = self.ws.store.get(name)
        return info.row_count if info else 0

    async def _write(self, current: Current, rows_tables: list[str], cards: list[Any]) -> list[str]:
        """.sab/: the manifest, Visualizations, the model, ticked rows; each only when its bytes change,
        and what is no longer there taken away. The files written."""
        folder = current.folder
        written: list[str] = []

        async def put(relative: str, body: bytes) -> None:
            try:
                if await asyncio.to_thread(self._archive.write_state, folder, relative, body):
                    written.append(relative)
            except FileNotFoundError as error:
                raise NotFound(str(error)) from None
            except PermissionError as error:
                raise Conflict(str(error)) from None

        async def drop(relative: str | None) -> None:
            if not relative:
                return
            gone: bool = await asyncio.to_thread(self._archive.remove_state, folder, relative)
            if gone:
                written.append(relative)

        earlier = current.manifest
        tables: list[TableEntry] = []
        for table in self._tables():
            table = rules.carried(earlier, table.name, table)
            if table.name in rows_tables and self.ws.store.get(table.name) is not None:
                entry = f"{rules.DATA_FOLDER}/{table.name}.parquet"
                rows = await self._rows_of(table.name)
                await put(entry, await asyncio.to_thread(self._archive.rows_bytes, rows))
                table = replace(table, rows_file=entry, source=replace(table.source, rows=True))
            elif table.name in current.waiting and table.rows_file:
                pass  # not back yet: its kept rows stay as they were
            else:
                table = replace(table, rows_file=None)
            tables.append(table)
        if rows_tables:
            await asyncio.to_thread(self._archive.ensure_ignored, folder, current.name)
        kept = {t.rows_file for t in tables if t.rows_file}
        for before in earlier.tables if earlier else ():
            if (
                before.rows_file
                and before.rows_file not in kept
                and before.rows_file.startswith(rules.DATA_FOLDER)
            ):
                await drop(before.rows_file)  # its tick taken off (or the table closed): its rows go
        shown = [c for c in cards if c.get("kind") != "theme"]
        visualizations = rules.VISUALIZATIONS_PATH if shown else None
        if visualizations:
            body = {"name": current.name, "versions": [{"cards": cards}]}
            text = json.dumps(body, default=str, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
            await put(visualizations, text.encode("utf-8"))
        else:
            await drop(rules.VISUALIZATIONS_PATH)
        model = self._models.model
        model_entry = rules.MODEL_PATH if model.tables() or model.relationships else None
        if model_entry:
            await put(model_entry, write_set(model).encode("utf-8"))
        else:
            await drop(rules.MODEL_PATH)
        layout = current.layout
        manifest = Manifest(
            name=current.name,
            tables=tuple(tables),
            app_version=self._version,
            tabs=layout.get("home") or {},
            workbench=layout.get("workbench") or {},
            diagram=layout.get("diagram") or {},
            visualizations=visualizations,
            model=model_entry,
            autosave=current.autosave,
            extra=(dict(earlier.extra) if earlier else self._type_extra(folder))
            | _extras(self.manifest_extras),
        )
        await put(rules.MANIFEST_PATH, rules.write_manifest(manifest).encode("utf-8"))
        current.manifest = manifest
        return written

    def _type_extra(self, folder: str) -> dict[str, Any]:
        """A project made with a type keeps it (services/projects.py wrote it before the first save)."""
        kind = self._projects.type_of(folder)
        return {} if kind == "bi" else {"type": kind}

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

    # ===== copy, import =====

    async def copy(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Copy project to: {"path": a new or empty folder, "data"?: true to copy .sab/data/ too, "folder"?:
        a project that is not open (default: the open one)}. The open one is saved first. The agent's copy
        with rows waits for the user's Allow."""
        body = body if isinstance(body, dict) else {}
        target = body.get("path")
        if not isinstance(target, str) or not target.strip():
            raise ValueError('Send {"path": a new or empty folder to copy the project to}.')
        target = self._full(target)
        source = body.get("folder")
        if isinstance(source, str) and source.strip():
            source = self._full(source)
        elif self.current is not None:
            source = self.current.folder
        else:
            raise NotFound("No project is open: name the project's folder to copy.")
        if not self._archive.is_folder(source):
            raise NotFound(f"{source} is not there.")
        data = body.get("data") is True
        if self.current is not None and self.current.folder == source and not self.current.read_only:
            if self.dirty():
                await self.save({}, AUTOSAVE)  # as Autosave would: the copy is of the project as it stands
        if data and who == "agent":
            detail = f"Copy the project with its kept rows (.sab/data):\n  {source}\n  to {target}"
            if not await self._approvals.ask(_base(source), "copy the project with rows", detail):
                raise Refused("The user declined (or did not answer): the project was not copied.")
        try:
            done = await asyncio.to_thread(self._archive.copy_project, source, target, data)
        except FileExistsError as error:
            raise Conflict(str(error)) from None
        self._recent.add(done, self._now())
        self.ws.audit.write(who, "copy_project", done, data=data)
        await self._changed()
        return {"copied": done, "from": source, "data": data}

    # ===== close, the layout, the recent list =====

    async def close(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Close the project: {"discard"?}. Asks first (Conflict) when it has unsaved changes."""
        body = body if isinstance(body, dict) else {}
        self._need()
        async with self._busy:
            self._check_discard(body)
            await self._clear(who)
            self._serial += 1
            self.ws.audit.write(who, "close_project", None)
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
        """Autosave on or off: {"on": true}. Kept in .sab/project.json at once (nothing else is saved by
        the switch)."""
        if not isinstance(body, dict) or not isinstance(body.get("on"), bool):
            raise ValueError('Send {"on": true} or {"on": false}.')
        current = self._need()
        if current.read_only:
            raise Refused(current.read_only)
        current.autosave = body["on"]
        current.autosave_error = None
        self._settling = None
        if current.manifest is not None:
            manifest = replace(current.manifest, autosave=current.autosave)
            try:
                await asyncio.to_thread(
                    self._archive.write_state,
                    current.folder,
                    rules.MANIFEST_PATH,
                    rules.write_manifest(manifest).encode("utf-8"),
                )
            except OSError as error:
                raise Conflict(f"The switch could not be kept in {current.folder}: {error}") from None
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
            or current.read_only
            or self._busy.locked()
            or self._key() == current.saved_key
        ):
            self._settling = None
            return False
        seen = self._key()
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
            raise ValueError('Send {"path": the project\'s folder}.')
        if not self._recent.remove(body["path"]):
            raise NotFound("That project is not in the list.")
        await self._changed()
        return self.recent()

    async def stop(self) -> None:
        """The server stops: nothing to tidy (the project is its folder)."""


def rules_path(folder: str, relative: str) -> str:
    """A path inside the project, whole (its separators as the folder's)."""
    sep = "\\" if "\\" in folder and "/" not in folder else "/"
    return folder.rstrip("\\/") + sep + relative.replace("/", sep)


def _extras(makers: list[Callable[[], dict[str, Any]]]) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for make in makers:
        found |= make()
    return found
