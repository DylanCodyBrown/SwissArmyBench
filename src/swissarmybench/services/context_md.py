"""context.md (domain/context_md.py): the app's live picture in Launch Claude's folder, kept current.

- **Gathered** from the services, metadata only (names, counts, types, steps in words): the open project,
  the connections (their cards' status, colour, a loaded catalog's first tables), the APIs and Structures
  when this build has them, the open tables (origin in words, columns, steps), the ERD's relationships,
  the variables (names and sources), the project's documents, what each window shows, the tool guide.
- **Written** into claude/<project or no-project>/context.md once a launch made that folder: looked at every
  couple of seconds (settings.context_md_seconds) after any notice to the pages (and every
  REFRESH_SECONDS all the same), rewritten once a change has settled for one look (a burst of changes is
  one write), atomically, and only when its text changed.
- **What the agent was given:** the digests of each section as of its last read (the launch, a prompt,
  `app_context`), so the prompt hook says in one line which sections changed since.
"""

from __future__ import annotations

import asyncio
import posixpath
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

from swissarmybench.domain import beta_log
from swissarmybench.domain import claude as claude_rules
from swissarmybench.domain import context_md as rules
from swissarmybench.domain.connection_colours import PALETTE
from swissarmybench.domain.steps import Step
from swissarmybench.domain.table_cells import Origin
from swissarmybench.services.workspace import Workspace

REFRESH_SECONDS = 30.0  # looked at again even with no notice (a variables file, a kernel's start)
MAX_USED_IN = 12


class ContextFiles(Protocol):
    def write_context(self, name: str, text: str, make: bool = False) -> str | None: ...

    def context_path(self, name: str) -> str | None: ...

    def index(self) -> str: ...

    def guide(self, topic: str) -> str: ...


Catalog = Callable[[str], Awaitable[tuple[list[str], list[rules.CatalogTable], int, set[str]] | None]]


def _file_name(path: str | None) -> str:
    return re.split(r"[\\/]", path or "")[-1]


def origin_words(origin: Origin) -> str:
    """Where a table came from, in words with no value: a connection and its place (never a query's text),
    a file's name (never its folder), Python, pasted, a query."""
    if origin.kind == "connection" and origin.connection:
        place = ".".join(p for p in (origin.place or ()) if p)
        text = f"connection {rules.code(origin.connection)}"
        if place:
            return f"{text}: {rules.code(place)}"
        return text + (", a DAX query" if origin.dax else ", a query" if origin.sql else "")
    if origin.kind in ("file", "dropped"):
        name = _file_name(origin.path or origin.filename)
        return f"file {rules.code(name)}" + (f", sheet {rules.code(origin.sheet)}" if origin.sheet else "")
    return {"python": "Python", "paste": "pasted", "query": "a query (the + tab)"}.get(origin.kind, "")


def _colour_name(colour: str | None) -> str | None:
    if not colour:
        return None
    names = {hex_.casefold(): name for name, hex_ in PALETTE}
    return names.get(colour.casefold(), colour)


class ContextMd:
    def __init__(
        self,
        ws: Workspace,
        files: ContextFiles,
        *,
        version: str,
        project: Callable[[], dict[str, Any] | None],
        connections: Callable[[], list[dict[str, Any]]],
        colour_of: Callable[[str], str | None],
        catalog: Catalog,
        used_in: Callable[[str], list[tuple[str, str]]],
        origin_of: Callable[[str], Origin],
        relationships: Callable[[], dict[str, Any]],
        variables: Callable[[], dict[str, Any]],
        documents: Callable[[], dict[str, Any]],
        windows: Callable[[], dict[str, Any]],
        changes: Callable[[], int],
        apis: Callable[[], dict[str, Any]] | None = None,
        structures: Callable[[], dict[str, Any]] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ws = ws
        self._files = files
        self._version = version
        self._project = project
        self._connections = connections
        self._colour_of = colour_of
        self._catalog = catalog
        self._used_in = used_in  # (kind, title): the documents and grids that use a connection
        self._origin_of = origin_of
        self._relationships = relationships
        self._variables = variables
        self._documents = documents
        self._windows = windows
        self._changes = changes
        # SEAM (trees-apis): the APIs page's listing ({"apis": [{name, title, operations, tables}]}) and
        # Structures' ({"open": [{name, format, origin, steps: [{words}], type, count}]}); None: not built.
        self._apis = apis
        self._structures = structures
        self._clock = clock
        self._lock = asyncio.Lock()
        self._looked: tuple[int, float] | None = None  # the notice count and time of the last look
        self._pending: rules.Rendered | None = None  # a change not yet settled
        self._written: dict[str, str] = {}  # folder name -> the text last written there
        self._seen: Mapping[str, str] | None = None  # the sections as the agent last read them
        self.last: rules.Rendered | None = None

    # ===== gathering =====

    def _folder(self) -> tuple[str | None, str]:
        """The open project's working folder (its own), and claude/'s folder name for it."""
        project = self._project() or {}
        name = project.get("name")
        return project.get("folder"), claude_rules.folder_name(str(name) if name else None)

    def _relative(self, path: str, folder: str | None) -> str:
        """A path as the project's own (relative to its folder); outside it, the file's name only."""
        clean = path.replace("\\", "/")
        if folder:
            root = folder.replace("\\", "/").rstrip("/") + "/"
            if clean.casefold().startswith(root.casefold()):
                return clean[len(root) :]
        return posixpath.basename(clean)

    async def _connection(self, card: Mapping[str, Any], folder: str | None) -> rules.ConnectionFacts:
        name = str(card["name"])
        state = card.get("catalog_state") or {}
        loaded = bool(card.get("catalog_loaded"))
        error: str | None = None
        if card.get("status") == "failing":
            said = str(state.get("error") or "") if state.get("state") == "failed" else ""
            error = beta_log.redact(said)[:300] if said else "its last call failed"
        schemas: list[str] = []
        tables: list[rules.CatalogTable] = []
        total, shared = 0, set[str]()
        catalog_state = "loaded" if loaded else state.get("state")
        if card.get("connection") != "vault":
            try:
                found = await self._catalog(name)
            except Exception:  # a catalog that cannot be read now: said not loaded
                found = None
            if found is not None:
                schemas, tables, total, shared = found
                catalog_state = "loaded"
        used = []
        try:
            for kind, title in self._used_in(name)[:MAX_USED_IN]:
                used.append(f"grid {title}" if kind == "grid" else self._relative(title, folder))
        except Exception:  # noqa: S110 (where it is used is a nicety: connections_usage has it)
            pass
        return rules.ConnectionFacts(
            name=name,
            kind=str(card.get("connection") or ""),
            type=str(card.get("type") or ""),
            template=card.get("template"),
            dialect=card.get("dialect"),
            colour=None if card.get("connection") == "vault" else _colour_name(self._colour_of(name)),
            status=str(card.get("status") or "ready"),
            error=error,
            needs=tuple(str(m) for m in card.get("missing") or ()),
            catalog=catalog_state,
            schemas=tuple(schemas),
            tables=tuple(tables),
            table_count=total,
            shared=frozenset(shared),
            used_in=tuple(dict.fromkeys(used)),
            writes=(card.get("writes") or {}).get("writable"),
        )

    def _tables(self) -> tuple[rules.TableFacts, ...]:
        ws = self.ws
        out = []
        for info in sorted(ws.store.all(), key=lambda i: i.name.casefold()):
            grids = ws.grids.for_dataset(info.name)
            steps: tuple[Step, ...] = (
                tuple(s for s in grids[0].steps if not s.params.get("header")) if grids else ()
            )
            out.append(
                rules.TableFacts(
                    info.name,
                    info.row_count,
                    tuple((c.name, c.type) for c in info.columns),
                    steps,
                    origin_words(self._origin_of(info.name)),
                    tuple(g.id for g in grids),
                )
            )
        return tuple(out)

    def _apis_facts(self) -> tuple[rules.ApiFacts, ...] | None:
        if self._apis is None:
            return None
        listed = self._apis().get("apis") or []
        return tuple(
            rules.ApiFacts(
                str(a.get("name")),
                str(a.get("title") or ""),
                int(a.get("operations") or 0),
                tuple(str(t) for t in a.get("tables") or ()),
            )
            for a in listed
        )

    def _structures_facts(self) -> tuple[rules.StructureFacts, ...] | None:
        if self._structures is None:
            return None
        out = []
        for s in self._structures().get("open") or []:
            count = s.get("count")
            shape = (
                f"{s.get('type')}" + (f" of {count:,}" if isinstance(count, int) else "")
                if s.get("type")
                else ""
            )
            origin = s.get("origin") or {}
            where = ""
            if isinstance(origin, dict):
                where = str(origin.get("api") or origin.get("kind") or "")
            out.append(
                rules.StructureFacts(
                    str(s.get("name")),
                    str(s.get("format") or ""),
                    shape,
                    rules.code(where) if where else "",
                    tuple(str(x.get("words") or "") for x in s.get("steps") or ()),
                )
            )
        return tuple(out)

    def _relationships_facts(self) -> tuple[rules.RelationshipFacts, ...]:
        model = self._relationships() or {}
        return tuple(
            rules.RelationshipFacts(
                str(r.get("from")),
                tuple(str(c) for c in r.get("from_columns") or ()),
                str(r.get("to")),
                tuple(str(c) for c in r.get("to_columns") or ()),
                str(r.get("kind") or "many-to-one"),
                r.get("active") is not False,
            )
            for r in model.get("relationships") or ()
        )

    def _variables_facts(self) -> tuple[rules.VariableFacts, ...]:
        listed = self._variables().get("variables") or []
        # Names and sources only: never a value (a plain one's included), never a secret's name in a vault.
        return tuple(
            rules.VariableFacts(
                str(v.get("name")), str(v.get("words") or v.get("from") or ""), v.get("vault")
            )
            for v in listed
        )

    def _documents_facts(self) -> tuple[rules.DocumentFacts, ...]:
        listed = self._documents().get("documents") or []
        return tuple(
            rules.DocumentFacts(str(d.get("kind")), str(d.get("path")), d.get("role"))
            for d in listed
            if not d.get("made")
        )

    def _windows_lines(self, folder: str | None) -> tuple[str, ...]:
        w = self._windows()
        lines = []
        if w.get("home"):
            front = w.get("front")
            grid = self.ws.grids.get(front) if front else None
            lines.append(
                "The home window: "
                + (
                    f"grid {rules.code(grid.id)} on {rules.code(grid.dataset)} in front"
                    if grid
                    else "no grid in front"
                )
            )
        if w.get("workbench"):
            running = [rules.code(self._relative(d, folder)) for d in w.get("kernels") or ()]
            lines.append(
                "The Workbench"
                + (f": kernels running for {', '.join(running)}" if running else ": no kernel running")
            )
        if w.get("blades"):
            lines.append("The blades page")
        return tuple(lines)

    async def state(self) -> rules.State:
        project = self._project() or {}
        folder, _ = self._folder()
        connections = []
        for card in self._connections():
            if card.get("tables_kind") == "api" and self._apis is not None:
                continue  # an API: its own section (APIs) has it and its tables
            connections.append(await self._connection(card, folder))
        return rules.State(
            version=self._version,
            project=project.get("name"),
            folder=folder,
            connections=tuple(connections),
            apis=self._apis_facts(),
            tables=self._tables(),
            structures=self._structures_facts(),
            relationships=self._relationships_facts(),
            variables=self._variables_facts(),
            documents=self._documents_facts(),
            windows=self._windows_lines(folder),
            index=self._files.index(),
            guide={topic: self._files.guide(topic) for topic in {t for t, _ in rules.GUIDE_SECTIONS}},
        )

    async def build(self) -> rules.Rendered:
        rendered = rules.render(await self.state(), self.ws.settings.context_md_chars)
        self.last = rendered
        return rendered

    # ===== writing =====

    def _write(self, rendered: rules.Rendered, make: bool = False) -> str | None:
        _, name = self._folder()
        if self._written.get(name) == rendered.text and not make:
            return self._files.context_path(name)
        path = self._files.write_context(name, rendered.text, make)
        if path is not None:
            self._written[name] = rendered.text
        return path

    async def tick(self) -> None:
        """One look: after a notice (or REFRESH_SECONDS), build; a changed text is written once it settled
        (the same at the next look), so a burst of changes is one write."""
        async with self._lock:
            if self._files.context_path(self._folder()[1]) is None:
                return  # no launch made this project's folder: nothing to keep current
            now, count = self._clock(), self._changes()
            fresh = (
                self._looked is not None
                and self._looked[0] == count
                and now - self._looked[1] < REFRESH_SECONDS
            )
            if fresh and self._pending is None:
                return
            if fresh and self._pending is not None:
                self._write(self._pending)  # nothing changed since the last look: it settled
                self._pending = None
                return
            self._looked = (count, now)
            rendered = await self.build()
            _, name = self._folder()
            if rendered.text == self._written.get(name):
                self._pending = None
            elif self._pending is not None and self._pending.text == rendered.text:
                self._write(rendered)
                self._pending = None
            else:
                self._pending = rendered

    async def flush(self, make: bool = False) -> tuple[rules.Rendered, str | None]:
        """Built and written now (a launch, a prompt, app_context): the text and the file's path."""
        async with self._lock:
            rendered = await self.build()
            self._looked = (self._changes(), self._clock())
            self._pending = None
            return rendered, self._write(rendered, make)

    async def run_forever(self) -> None:
        while True:
            await asyncio.sleep(self.ws.settings.context_md_seconds)
            try:
                await self.tick()
            except Exception:  # noqa: S112 (a look that failed: the next one tries again)
                continue

    # ===== what the agent was given =====

    async def launched(self) -> str | None:
        """Launch Claude made the folder: context.md written there now, and taken as read (Claude Code
        loads it at start through CLAUDE.md's import)."""
        rendered, path = await self.flush(make=True)
        self._seen = rendered.digests
        return path

    async def read(self, who: str) -> dict[str, Any]:
        """The text (the resource swissarmybench://context, app_context): the agent's read counts as seen."""
        rendered, path = await self.flush()
        if who == "agent":
            self._seen = rendered.digests
        return {
            "text": rendered.text,
            "path": path,
            "sections": list(rendered.digests),
            "trimmed": list(rendered.trims),
        }

    async def prompt(self) -> dict[str, Any]:
        """The prompt hook's question: the sections changed since the agent's last read (none on its first
        prompt: `first`), the file written first so it says what the line says."""
        rendered, path = await self.flush()
        first = self._seen is None
        changed = rules.changed(self._seen, rendered.digests)
        self._seen = rendered.digests
        line = rules.first_line(path) if first else rules.changed_line(path or "`app_context`", changed)
        return {"path": path, "first": first, "changed": changed, "line": line}
