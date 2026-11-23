"""The shared catalog (domain/shared_catalog.py has the rules): the library's catalog/<connection>.json, kept
by what happens here and read again when the user's pulls change it.

  written   on the event, for the user as for the agent: a connection saved (its file, its kind); its tables
            listed (Refresh, a catalog loading itself, the Connections page's tree: present and gone); the
            relationships in use changed or a project's model opened (keys and relationships added; one the
            user deleted taken out); a project opened or saved (its name in used_by of the tables it uses)
  pruned    a connection deleted: its file removed; a table not listed by a successful listing: gone, then
            removed after settings.shared_catalog_prune_days; a failed listing changes nothing
  read      the folder looked at every settings.shared_catalog_seconds (the files' stamps; nothing new
            installed): a file changed from outside (a pull) is read again, the pages told (catalog_changed)
            with "Catalog updated from the library: 3 connections changed"; Refresh (the agent's
            catalog_shared_refresh) looks now
  bad file  conflict markers or broken JSON: said with its name (problems) and skipped; nothing writes over it
            until it reads again (the user finishes the merge)

The app never runs git and sends nothing anywhere: the folder is the user's working copy.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from swissarmybench.domain import connection_tables as connection_table_rules
from swissarmybench.domain import connections as connection_rules
from swissarmybench.domain import shared_catalog as rules
from swissarmybench.domain.blades import Blade
from swissarmybench.domain.relationships import Model, code_of, from_connection
from swissarmybench.services.workspace import Workspace

Stamp = tuple[int, int]
ListingRows = list[tuple[str, str, str, str, str, str, bool | None]]


class Files(Protocol):
    """adapters/shared_catalog.py CatalogFiles."""

    def stamps(self) -> dict[str, Stamp]: ...

    def stamp(self, name: str) -> Stamp | None: ...

    def read(self, name: str) -> str | None: ...

    def write(self, name: str, text: str) -> bool: ...

    def remove(self, name: str) -> bool: ...


@dataclass(frozen=True)
class Here:
    """A connection on this computer: its name, kind and starter."""

    name: str
    kind: str
    template: str


def connections_here(blades: Iterable[Blade]) -> list[Here]:
    """This computer's connections that have tables (never a web call, nor a key vault: it has no tables)."""
    found = []
    for blade in blades:
        if blade.web_call or connection_rules.connection_kind(blade.kind, blade.template) is None:
            continue
        kind = connection_table_rules.tables_kind(
            blade.kind, blade.template, blade.dialect, blade.catalog_language, blade.tags, blade.code
        )
        if kind is not None:
            found.append(Here(blade.name, kind, str(blade.template or "")))
    return found


# None with no project open, else the project's folder name, its table names, and its documents (path, text).
ProjectUse = Callable[[], tuple[str, set[str], list[tuple[str, str]]] | None]


class SharedCatalog:
    def __init__(
        self,
        ws: Workspace,
        files: Files,
        connections: Callable[[], list[Here]],
        rows: Callable[[str], Awaitable[ListingRows | None]],
        model: Callable[[], Model],
        today: Callable[[], str],
        now: Callable[[], str],
        project: ProjectUse,
    ) -> None:
        self.ws = ws
        self._files = files
        self._connections = connections
        self._rows = rows
        self._model = model
        self._today = today
        self._now = now
        self._project = project
        self._catalogs: dict[str, rules.Catalog] = {}  # by file name
        self._problems: dict[str, str] = {}  # by file name: why it does not read
        self._stamps: dict[str, Stamp] = {}  # what was last read or written, by file name
        self._seen: set[Any] = set()  # the relationships in use when last told (their keys)
        self.picked_up: str = ""  # when a change from the folder was last picked up (a date and time)
        self._lock = asyncio.Lock()

    # ===== reading the folder =====

    def load(self) -> None:
        """Every file read (at start, and when the library folder moves): nothing said."""
        self._catalogs.clear()
        self._problems.clear()
        self._stamps = self._files.stamps()
        for name in self._stamps:
            self._read(name)
        self._seen = {rules.Join.of(r).key for r in self._model().relationships}

    def _read(self, name: str) -> None:
        text = self._files.read(name)
        if text is None:
            self._catalogs.pop(name, None)
            self._problems.pop(name, None)
            return
        try:
            self._catalogs[name] = rules.parse(text, f"{rules.FOLDER}/{name}")
            self._problems.pop(name, None)
        except rules.CatalogFileError as error:
            self._catalogs.pop(name, None)
            self._problems[name] = str(error)

    async def refresh(self, who: str = "user") -> dict[str, Any]:
        """Look at the folder now: what changed from outside read again, the pages told. What changed."""
        async with self._lock:
            now = await asyncio.to_thread(self._files.stamps)  # the folder's glob and stats, off the loop
            changed = sorted(
                {n for n in now if self._stamps.get(n) != now[n]} | {n for n in self._stamps if n not in now}
            )
            for name in changed:
                self._read(name)
            self._stamps = now
        if changed:
            self.picked_up = self._now()
            await self.ws.live.broadcast(
                {
                    "type": "catalog_changed",
                    "from": "folder",
                    "changed": len(changed),
                    "words": rules.changed_words(len(changed)),
                }
            )
        if who == "agent" or (who == "user" and changed):
            self.ws.audit.write(who, "catalog_shared_refresh", None, changed=len(changed))
        return self.info() | {"changed": [f"{rules.FOLDER}/{n}" for n in changed]}

    async def run_forever(self) -> None:
        while True:
            await asyncio.sleep(self.ws.settings.shared_catalog_seconds)
            try:
                await self.refresh("app")
            except Exception:  # noqa: S112 (a look that failed: the next one tries again)
                continue

    # ===== writing on the events =====

    def _here(self, name: str) -> Here | None:
        return next((c for c in self._connections() if c.name.casefold() == name.casefold()), None)

    async def _update(self, here: Here, change: Callable[[rules.Catalog], rules.Catalog]) -> bool:
        """The connection's file read as it is on disk, changed, written when its bytes change. A file that
        does not read is left alone (said in problems). Whether it was written."""
        name = rules.file_name(here.name)
        async with self._lock:
            text = self._files.read(name)
            if text is not None:
                try:
                    current = rules.parse(text, f"{rules.FOLDER}/{name}")
                except rules.CatalogFileError as error:
                    self._problems[name] = str(error)
                    return False
            else:
                current = rules.Catalog(here.name)
            made = change(rules.Catalog(here.name, here.kind, here.template, current.tables))
            written = self._files.write(name, rules.render(made))
            self._catalogs[name] = made
            self._problems.pop(name, None)
            stamp = self._files.stamp(name)
            if stamp is not None:
                self._stamps[name] = stamp
        if written:
            await self.ws.live.broadcast({"type": "catalog_changed", "from": "app", "connection": here.name})
        return written

    def _with_model(self, catalog: rules.Catalog) -> rules.Catalog:
        return rules.with_model(catalog, self._model())

    async def saved(self, name: str) -> None:
        """A connection saved here: its file (its kind; the relationships in use that are its)."""
        here = self._here(name)
        if here is not None:
            await self._update(here, self._with_model)

    async def listed(self, name: str) -> None:
        """A connection's tables listed (successfully): present and gone, then the model's keys."""
        here = self._here(name)
        if here is None:
            return
        found = await self._rows(here.name)
        if found is None:
            return
        rows = [rules.Listed(d, s, t, c, ty, n, k) for d, s, t, k, c, ty, n in found]
        today, days = self._today(), self.ws.settings.shared_catalog_prune_days
        await self._update(here, lambda c: self._with_model(rules.listed(c, rows, today, days)))
        await self._use_project_on(here)

    async def removed(self, name: str, who: str) -> dict[str, Any]:
        """A connection deleted: its catalog file goes too."""
        file = rules.file_name(name)
        async with self._lock:
            if file in self._problems:
                return {"catalog_removed": False}
            gone = self._files.remove(file)
            self._catalogs.pop(file, None)
            self._stamps.pop(file, None)
        if gone:
            self.ws.audit.write(who, "catalog_shared_remove", name)
            await self.ws.live.broadcast({"type": "catalog_changed", "from": "app", "connection": name})
        return {"catalog_removed": gone}

    async def relationships(self, how: str) -> None:
        """The relationships in use changed ("edit": one gone was deleted) or a project's model came in
        ("replace": nothing is taken out): every connection's file here follows. Its trouble is kept here."""
        try:
            await self._relationships(how)
        except Exception:  # noqa: S110 (a file that could not be written never undoes the user's change)
            pass

    async def _relationships(self, how: str) -> None:
        model = self._model()
        keys = {rules.Join.of(r).key for r in model.relationships}
        removed = [] if how != "edit" else [_join(k) for k in self._seen - keys]
        self._seen = keys
        for here in self._connections():
            if rules.file_name(here.name) not in self._catalogs and not _names(model, here.name):
                continue  # nothing of it here yet: its file comes with its save or listing
            await self._update(here, lambda c: rules.with_model(rules.without_joins(c, removed), model))

    async def project_used(self, folder: str | None = None) -> None:
        """The open project (opened or saved): its name in used_by of each table it uses, out of the rest."""
        for here in self._connections():
            await self._use_project_on(here)

    async def _use_project_on(self, here: Here) -> None:
        found = self._project()
        if found is None:
            return
        project, names, documents = found
        catalog = self._catalogs.get(rules.file_name(here.name))
        if catalog is None:
            return
        texts = [code_of(path, text) for path, text in documents]
        used = rules.used_names(catalog, names, texts)
        await self._update(here, lambda c: rules.with_usage(c, project, used))

    # ===== reading it =====

    def catalogs(self) -> dict[str, rules.Catalog]:
        """Each connection's catalog that reads, by its connection's name."""
        return {c.connection: c for c in self._catalogs.values()}

    def here_names(self) -> set[str]:
        return {c.name.casefold() for c in self._connections()}

    def problems(self) -> list[dict[str, str]]:
        return [{"file": f"{rules.FOLDER}/{n}", "error": e} for n, e in sorted(self._problems.items())]

    def info(self) -> dict[str, Any]:
        """Settings' Library: the catalog's counts and when a change from the folder was last picked up."""
        catalogs = list(self._catalogs.values())
        here = self.here_names()
        return {
            "connections": len(catalogs),
            "tables": sum(1 for c in catalogs for t in c.tables.values() if t.state == rules.PRESENT),
            "gone": sum(1 for c in catalogs for t in c.tables.values() if t.state == rules.GONE),
            "not_here": sorted(c.connection for c in catalogs if c.connection.casefold() not in here),
            "picked_up": self.picked_up,
            "problems": self.problems(),
        }

    def listing(self, search: Any = None) -> dict[str, Any]:
        """Every connection in the shared catalog with its tables' names, state and used_by (search: words
        in a connection's or table's name)."""
        found = rules.listing(self.catalogs(), self.here_names())
        words = str(search or "").casefold().split()
        if words:
            for c in found:
                c["tables_list"] = [
                    t
                    for t in c["tables_list"]
                    if all(w in f"{c['connection']} {t['key']}".casefold() for w in words)
                ]
            found = [c for c in found if c["tables_list"]]
        return {"connections": found} | {k: v for k, v in self.info().items() if k != "connections"}

    def table(self, connection: Any, table: Any) -> dict[str, Any]:
        if not isinstance(connection, str) or not isinstance(table, str) or not connection or not table:
            raise ValueError("Name the connection and the table: ?connection=Warehouse&table=dbo.Orders")
        catalog, found = rules.find_table(self.catalogs(), connection, table)
        return rules.table_json(catalog, found) | {"here": catalog.connection.casefold() in self.here_names()}

    def model(self) -> Model:
        """The shared catalog as a model (the ERD's All tables)."""
        return rules.model_of(self._catalogs.values())

    def tables(self) -> Iterable[tuple[rules.Catalog, rules.Table]]:
        for c in self._catalogs.values():
            for t in c.tables.values():
                if t.state == rules.PRESENT:
                    yield c, t


def _join(key: Any) -> rules.Join:
    from_table, from_columns, to_table, to_columns = key
    return rules.Join(from_table, from_columns, to_table, to_columns)


def _names(model: Model, connection: str) -> bool:
    return any(from_connection(s, connection) for s in model.sources.values())
