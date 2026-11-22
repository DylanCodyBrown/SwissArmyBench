"""The project scaffold kept as the user works (domain/scaffold.py; Plans/adapter.plan.md "Who writes what").

  status   each made file: written, the same, to write, to remove, or edited by hand (kept: its text and the
           app's beside it, for Compare)
  refresh  every made file brought up to date: adapter.py (the app's own bytes, once something reads through
           it), connections.py (a section per connection the project uses), README.md's Variables block,
           data.py's structures read as grids, and the sandbox mirror (sandbox_data.py,
           sandbox_connections.py); only the files whose bytes change, never one edited by hand, nothing for
           what the project never uses
  take     {"file"}: the app's text over a hand edit (Take the new one)
  soon     a refresh once the notices settle (a connection saved, a table opened, the sandbox changed, a
           variable set, API.py or data.ipynb saved): the files grow as the user works, never all at once

The base reads what a project type adds from its contract.json (domain/project_contract.py): the core files
are the base's, and it never names an extension's file. The agent's refresh and take are its own (no Allow:
the
files hold names only, never a value).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from swissarmybench.domain import project_contract
from swissarmybench.domain import scaffold as rules
from swissarmybench.services.workspace import Conflict, Refused, Workspace

SETTLE = 1.5  # seconds a burst of notices waits before one refresh
# The notices that can change a made file (heard on the live channel).
HEARD: frozenset[str] = frozenset(
    {
        "blades_changed",  # a connection saved, renamed or removed
        "sandbox_changed",
        "variables_changed",
        "project_changed",
        "project_documents_changed",
        "dataset_updated",
        "dataset_closed",
        "grid_shown",
        "file_changed",  # API.py, data.ipynb, a script saved (never the scaffold's own: by "app")
        "local_api_changed",
        "structures_changed",
    }
)


class Files(Protocol):
    """A project folder's own files (adapters/scaffold.py)."""

    def read(self, folder: str, relative: str) -> str | None: ...

    def write(self, folder: str, relative: str, text: str) -> None: ...

    def remove(self, folder: str, relative: str) -> None: ...


@dataclass
class Sources:
    """What the made files are made from (bootstrap.py wires each)."""

    used: Callable[[], list[str]]  # the connections the open project uses, in the order they were made
    connections: Callable[[list[str]], dict[str, Any]]  # services/script_export.py connections_code
    adapter: Callable[[], str]  # the app's adapter.py, its bytes
    variables: Callable[[], dict[str, str]]  # each variable's source in words (names only)
    documents_using: Callable[[str], list[str]] = lambda name: []  # the project's documents naming ${NAME}
    sandbox: Callable[[], Awaitable[dict[str, Any] | None]] | None = None  # its tables, baseline, checkpoints
    structures: Callable[[], list[rules.StructureGrid]] = lambda: []
    endpoints: Callable[[str], int] = lambda text: 0  # how many endpoints API.py's text has (none: commented)
    # The open project type's contract.json (domain/project_contract.py), None for the base's own: what its
    # deliverable adds beside the core files, listed as the contract says (the base never names one).
    contract: Callable[[str], dict[str, Any] | None] = lambda folder: None
    names: Callable[[str], list[str]] = lambda folder: []  # the project's files, relative (for the listing)
    edited: Callable[[str], set[str]] = lambda folder: set()  # .sab/hand-edited.json
    touched: Callable[[str, str], Awaitable[Any]] | None = None  # code_files: the file_changed notice
    extra: list[str] = field(default_factory=list)  # always the base's: never an extension's file


class Scaffold:
    def __init__(
        self, ws: Workspace, project: Callable[[], tuple[str, str] | None], files: Files, sources: Sources
    ) -> None:
        self.ws = ws
        self._project = project
        self._files = files
        self._sources = sources
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[Any] | None = None

    # ===== what each file should hold =====

    async def wanted(self, folder: str, title: str) -> tuple[dict[str, str | None], dict[str, Any]]:
        """Each made file's text (None: nothing uses it), and the facts said with it."""
        used = [n for n in await asyncio.to_thread(self._sources.used) if n.casefold() != "sandbox"]
        made: dict[str, Any] = (
            await asyncio.to_thread(self._sources.connections, used) if used else {"text": "", "readers": {}}
        )
        connections = rules.connections_py(str(made["text"])) if used and made.get("text") else None
        sandbox = await self._sources.sandbox() if self._sources.sandbox is not None else None
        tables: Mapping[str, Mapping[str, Any]] = (sandbox or {}).get("tables") or {}
        api = self._files.read(folder, rules.API)
        has_api = api is not None and self._sources.endpoints(api) > 0
        reads = connections is not None or has_api or bool(tables)
        wanted: dict[str, str | None] = {
            rules.ADAPTER: self._sources.adapter() if reads else None,
            rules.CONNECTIONS: connections,
            rules.SANDBOX_DATA: rules.sandbox_data_py(
                tables, (sandbox or {}).get("baseline_at"), (sandbox or {}).get("checkpoints") or []
            ),
            rules.SANDBOX_CONNECTIONS: rules.sandbox_connections_py(tables),
        }
        readers: Mapping[str, list[str]] = made.get("readers") or {}
        sources = self._sources.variables()
        names = list(dict.fromkeys([*readers, *(v for v in sources if self._sources.documents_using(v))]))
        variables = [
            rules.Variable(
                v,
                sources.get(v, ""),
                tuple(dict.fromkeys([*readers.get(v, []), *self._sources.documents_using(v)])),
            )
            for v in sorted(names, key=str.casefold)
        ]
        readme = self._files.read(folder, rules.README)
        wanted[rules.README] = rules.with_variables(readme, variables, title)
        data_py = self._files.read(folder, rules.DATA)
        if data_py is not None:
            wanted[rules.DATA] = rules.with_structures(data_py, self._sources.structures())
        return wanted, {
            "connections": used,
            "variables": [v.name for v in variables],
            "deliverable": self._deliverable(folder),
        }

    def _deliverable(self, folder: str) -> dict[str, Any]:
        """The project type's own files, from its contract.json: each with who owns it, what it is made from,
        what grows it, and whether the project has it yet."""
        contract = self._sources.contract(folder)
        if contract is None:
            return {"type": None, "files": []}
        names = self._sources.names(folder)
        files = [
            {
                "path": entry["path"],
                "owner": entry["owner"],
                "about": entry["about"],
                "made_from": entry["made_from"],
                "grows_on": list(entry["grows_on"]),
                "present": any(project_contract.matches(n, entry["path"]) for n in names),
            }
            for entry in contract["files"]
        ]
        return {"type": contract["type"], "deliverable": contract["deliverable"], "files": files}

    async def _plan(
        self, folder: str, title: str, take: Iterable[str] = ()
    ) -> tuple[rules.Plan, dict[str, Any], dict[str, str | None], dict[str, str | None]]:
        wanted, facts = await self.wanted(folder, title)
        have = {p: self._files.read(folder, p) for p in wanted}
        written = rules.read_state(self._files.read(folder, rules.STATE))
        # README.md and data.py are the user's and data.ipynb's: only their marked part is the app's, so a
        # change elsewhere in them is never a hand edit of the app's part (it is kept as it is).
        for shared in (rules.README, rules.DATA):
            if have.get(shared) is not None:
                written[shared] = rules.digest(have[shared] or "")
        hand = self._sources.edited(folder) - {rules.README}
        return rules.plan(wanted, have, written, hand, take), facts, wanted, have

    def _where(self) -> tuple[str, str]:
        found = self._project()
        if found is None:
            raise Conflict("Open a project first: its scaffold is its folder's files.")
        return found

    # ===== the calls =====

    async def status(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        folder, title = self._where()
        made, facts, wanted, have = await self._plan(folder, title)
        return self._answer(made, facts, wanted, have, written=False)

    async def refresh(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        folder, title = self._where()
        take = [str(f) for f in (body or {}).get("take") or []] if isinstance(body, dict) else []
        async with self._lock:
            made, facts, wanted, have = await self._plan(folder, title, take)
            state = rules.read_state(self._files.read(folder, rules.STATE))
            changed: list[str] = []
            for change in made.changes:
                if change.action == "write":
                    text = wanted[change.path] or ""
                    self._files.write(folder, change.path, text)
                    state[change.path] = rules.digest(text)
                    changed.append(change.path)
                elif change.action == "remove":
                    self._files.remove(folder, change.path)
                    state.pop(change.path, None)
                    changed.append(change.path)
                elif change.action == "same" and change.path in rules.MADE:
                    state[change.path] = rules.digest(wanted[change.path] or "")
                elif change.action == "none":
                    state.pop(change.path, None)
            state = {p: h for p, h in state.items() if p in rules.MADE}
            text = rules.state_text(state)
            if text != (self._files.read(folder, rules.STATE) or "") and (
                state or self._files.read(folder, rules.STATE)
            ):
                self._files.write(folder, rules.STATE, text)
        for path in changed:
            if self._sources.touched is not None:
                await self._sources.touched(f"{folder.rstrip('/')}/{path}", "app")
        if changed:
            self.ws.audit.write(who, "scaffold_refresh", ", ".join(changed))
            await self.ws.live.broadcast({"type": "scaffold_changed", "files": changed})
        return self._answer(made, facts, wanted, have, written=True)

    async def take(self, body: Any, who: str = "user") -> dict[str, Any]:
        """Take the new one: the app's text over a made file edited by hand."""
        wanted = body.get("file") if isinstance(body, dict) else None
        if wanted not in rules.MADE and wanted not in (rules.README, rules.DATA):
            raise Refused(f"file is one of the made files: {', '.join(rules.MADE)}.")
        return await self.refresh({"take": [wanted]}, who)

    @staticmethod
    def _answer(
        made: rules.Plan,
        facts: dict[str, Any],
        wanted: Mapping[str, str | None],
        have: Mapping[str, str | None],
        written: bool,
    ) -> dict[str, Any]:
        files = [
            {"file": c.path, "state": c.action, "words": c.words, "made_from": rules.MADE.get(c.path, "")}
            for c in made.changes
            if c.action != "none"
        ]
        kept = [
            {"file": c.path, "yours": have.get(c.path) or "", "theirs": wanted.get(c.path) or ""}
            for c in made.changes
            if c.action == "edited"
        ]
        key = "written" if written else "to_write"
        return {
            "files": files,
            key: made.by("write"),
            "removed" if written else "to_remove": made.by("remove"),
            "kept": kept,
            **facts,
        }

    # ===== an export's core files =====

    async def export_core(self, connections: list[str]) -> dict[str, Any]:
        """adapter.py and connections.py for an export that reads these connections (a canvas's
        `[Conn].table`): the project's own core files as the scaffold makes them, their requirements and
        variables (names only). No connection: nothing."""
        wanted = [n for n in dict.fromkeys(connections) if n.casefold() != "sandbox"]
        if not wanted:
            return {"files": {}, "requirements": [], "variables": []}
        made = await asyncio.to_thread(self._sources.connections, wanted)
        if not made.get("text"):
            return {"files": {}, "requirements": [], "variables": []}
        # An API's connection loads its client (API_<name>.py) from this computer's library: an export
        # carries the file and loads it from beside connections.py.
        text, clients = rules.clients_beside(str(made["text"]))
        carried: dict[str, str] = {}
        for module, path in clients.items():
            folder, _, name = path.replace("\\", "/").rpartition("/")
            found = await asyncio.to_thread(self._files.read, folder, name)
            if found is not None:
                carried[f"{module}.py"] = found
        return {
            "files": {
                rules.ADAPTER: self._sources.adapter(),
                rules.CONNECTIONS: rules.connections_py(text),
            }
            | carried,
            "requirements": [*made.get("requirements", []), "duckdb>=1.1", "pyarrow>=15"],
            "variables": list(made.get("variables", [])),
        }

    # ===== as the user works =====

    def heard(self, message: Mapping[str, Any]) -> None:
        """A live notice (adapters/live_updates.py's listeners): a refresh once a burst of them settles,
        never for the scaffold's own writes."""
        kind = str(message.get("type") or "")
        if kind not in HEARD or self._project() is None:
            return
        if kind == "file_changed" and str(message.get("by") or "") == "app":
            return
        self.soon()

    def soon(self) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = asyncio.ensure_future(self._later())

    async def _later(self) -> None:
        try:
            await asyncio.sleep(SETTLE)
            await self.refresh(None, "app")
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: S110 (a file that could not be made never undoes the user's work)
            pass
