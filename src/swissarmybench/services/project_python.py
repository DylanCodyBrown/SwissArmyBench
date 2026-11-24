"""One Python per project (the owner, 2026-11-21; Plans/environment.plan.md, step 4; rules in
domain/project_python.py): the project's own `.venv` at its top, made by the app on New project and on
opening a project that has none (in the background: the page is never held, and the app's own Python runs
the code until it is ready), and what a notebook's older environment of its own offers the project.

The one session every document of the project runs in is the Workbench's (services/workbench.py asks
`session()` here for the folder and the Python); this service ends it when the project changes.

Notices: `project_python` {status, words, said?} when the making starts, ends or fails, and when a
notebook's older environment was read (its one line).

ProjectInstalls (the owner, 2026-11-23: "when a project opens, auto detect all the installs needed and
install them all at once with a informative progress bar"; rules in domain/project_needs.py): as a project
opens (and once its `.venv` is made), everything it needs is worked out off the loop and what its Python lacks
is installed in ONE install, its progress read from the installer's own lines. Notice: `project_installs`, the
whole state each time ({state, total, done, current, packages, words, problem, ...}).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from swissarmybench.domain import blades as blade_rules
from swissarmybench.domain import connection_kinds, project_paths
from swissarmybench.domain import environment as requirements_rules
from swissarmybench.domain import project_needs as needs_rules
from swissarmybench.domain import project_python as rules
from swissarmybench.domain.blades import Blade
from swissarmybench.services.hooks import Hooks
from swissarmybench.services.ports import Approvals
from swissarmybench.services.workspace import Conflict, Workspace


class Files(Protocol):
    """The project's Python as files (adapters/environment.py): nothing runs."""

    def python_of(self, folder: str | None) -> tuple[str, bool]: ...

    def read_requirements(self, folder: str) -> str: ...

    def installed(self, python: str) -> dict[str, str]: ...

    def requires(self, python: str) -> dict[str, list[str]]: ...

    def write_requirements(self, folder: str, text: str) -> bool: ...

    def project_code(self, folder: str) -> list[tuple[str, str]]: ...


Make = Callable[[str, list[str]], Awaitable[tuple[int | None, str]]]


class ProjectPython:
    def __init__(
        self,
        ws: Workspace,
        files: Files,
        make: Make,
        enabled: bool = True,
        end_session: Callable[[], Awaitable[Any]] | None = None,
        session_kernel: Callable[[], str | None] = lambda: None,
        forget_environment: Callable[[str], None] | None = None,
        type_requirements: Callable[[str], list[str]] = lambda folder: [],
    ) -> None:
        self.ws = ws
        self.files = files
        self._make = make
        self._enabled = enabled  # off: no `.venv` is made by itself (tests; SWISSARMYBENCH_PROJECT_VENV=off)
        self._folder: str | None = None
        self._making: dict[str, asyncio.Task[None]] = {}  # by project folder
        self._problems: dict[str, str] = {}
        self._offers: list[dict[str, Any]] = []  # notebooks' older environments, read once (memory only)
        # The Workbench's part: the project's session ended, and a document's remembered environment
        # forgotten once it was read.
        self.end_session: Callable[[], Awaitable[Any]] | None = end_session
        self.session_kernel: Callable[[], str | None] = session_kernel
        self.forget_environment: Callable[[str], None] | None = forget_environment
        # What the project's type needs in its `.venv` beyond requirements.txt (extensions.requirements_of:
        # Streamlit for a canvas), by the project's folder.
        self.type_requirements: Callable[[str], list[str]] = type_requirements
        # What the project needs, installed at once as it opens (ProjectInstalls; the composition root's).
        self.installs: ProjectInstalls | None = None

    # ===== what the screens and the Workbench read =====

    def _state(self) -> rules.State:
        folder = self._folder
        python, own = self.files.python_of(folder)
        return rules.State(
            folder,
            python,
            own,
            making=folder is not None and folder in self._making,
            problem=self._problems.get(folder) if folder else None,
        )

    def state(self) -> dict[str, Any]:
        """{"status": none | making | ready | missing | failed, "words", "python", "own", "problem",
        "session": the one session's words (a project only), "folder", "kernel": the session's while it
        runs, "offers": [...]}."""
        state = self._state()
        return {
            "status": state.status,
            "words": state.words,
            "python": state.python,
            "own": state.own,
            "problem": state.problem,
            "session": rules.SESSION_WORDS if state.folder else None,
            "folder": state.folder,
            "kernel": self.session_kernel() if state.folder else None,
            "offers": list(self._offers),
        }

    def session(self) -> tuple[str, str] | None:
        """The open project's folder and the Python its one session runs in (its `.venv` once it is there,
        else the app's own); None with no project open."""
        if self._folder is None:
            return None
        return self._folder, self.files.python_of(self._folder)[0]

    def auto(self) -> bool:
        """Whether the project's Python and installs are made by themselves (SWISSARMYBENCH_PROJECT_VENV)."""
        return self._enabled

    # ===== the project's `.venv` =====

    async def _say(self, said: str | None = None) -> None:
        await self.ws.live.broadcast({"type": "project_python", "said": said} | self.state())

    async def project_changed(self, folder: str | None) -> None:
        """A project opened, was made or closed: the session of the one before ends, and a project with no
        `.venv` gets one made in the background (said in one line, never waited for)."""
        if folder == self._folder:
            return
        self._folder = folder
        self._offers = []
        if self.end_session is not None:
            await self.end_session()
        making = folder is not None and self._enabled and not self.files.python_of(folder)[1]
        if making and folder is not None:
            self._start(folder)
            await self._say(rules.STATUS_WORDS["making"])
        else:
            await self._say()  # the pages follow the project: its Python, its one session
        if self.installs is not None:  # what it needs: once its `.venv` is there (made first when it is not)
            await self.installs.project_changed(folder, auto=self._enabled and not making)

    def _start(self, folder: str) -> None:
        if folder in self._making:
            return
        self._problems.pop(folder, None)
        task = asyncio.ensure_future(self._run(folder))
        self._making[folder] = task

    async def _run(self, folder: str) -> None:
        try:
            text = await asyncio.to_thread(self.files.read_requirements, folder)
            code, out = await self._make(folder, rules.venv_packages(text, self.type_requirements(folder)))
            problem = rules.made_words(code, out)
            if problem is None and not self.files.python_of(folder)[1]:
                problem = "Making the project's Python ended without a Python in its .venv folder."
        except asyncio.CancelledError:
            self._making.pop(folder, None)
            raise
        except Exception as error:  # the tool is missing, the folder cannot be written
            problem = rules.made_words(1, str(error))
        self._making.pop(folder, None)
        if problem:
            self._problems[folder] = problem
        self.ws.audit.write("app", "project_python_made" if problem is None else "project_python_failed", "")
        if folder == self._folder:
            await self._say(problem or rules.READY_WORDS)
            if problem is None and self.installs is not None and self._enabled:
                await self.installs.project_changed(folder, auto=True, again=True)

    async def make(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Make the project's `.venv` now (Try again after a failure, or a project opened while the making
        was switched off). Answers at once: the `project_python` notice says when it is ready."""
        folder = self._folder
        if folder is None:
            raise Conflict("A Python of its own is a project's: open or make one first (Home).")
        if self.files.python_of(folder)[1]:
            raise Conflict("This project already has its own Python (.venv in its folder).")
        self._start(folder)
        self.ws.audit.write(who, "project_python_make", "")
        await self._say(rules.STATUS_WORDS["making"])
        return self.state()

    async def wait(self) -> None:
        """Until the making under way has ended (tests, and the server's stop)."""
        for task in list(self._making.values()):
            await asyncio.wait([task])

    async def stop(self) -> None:
        for task in list(self._making.values()):
            task.cancel()
        self._making.clear()
        if self.installs is not None:
            await self.installs.stop()

    # ===== a notebook that had its own environment =====

    def moved(self, path: str, python: str) -> dict[str, Any] | None:
        """A document of the project opened with a Python remembered for it alone (a per-notebook
        environment from before): read once. Its chosen libraries the project lacks are offered for
        requirements.txt, the document's own choice is forgotten, and one line says so. None: nothing to say
        (it was the project's own Python)."""
        folder = self._folder
        if folder is None:
            return None
        project_python, _ = self.files.python_of(folder)
        # The project's own Python, or the app's own, is no environment of the notebook's: nothing to offer.
        if _same(python, project_python) or _same(python, self.files.python_of(None)[0]):
            if self.forget_environment is not None:
                self.forget_environment(path)
            return None
        try:
            there = rules.chosen(self.files.requires(python))
            libraries = rules.offered(
                there, self.files.read_requirements(folder), self.files.installed(project_python)
            )
        except OSError:
            libraries = []
        if self.forget_environment is not None:
            self.forget_environment(path)
        offer = {"document": path, "libraries": libraries, "words": rules.offer_words(path, libraries)}
        self._offers = [o for o in self._offers if o["document"] != path]
        if libraries:
            self._offers.append(offer)
        self.ws.audit.write("app", "notebook_environment_moved", path)
        return offer

    async def settle_offer(self, body: Any, who: str = "user") -> dict[str, Any]:
        """{"document"}: its offer is done with (its libraries were added, or Not now)."""
        document = body.get("document") if isinstance(body, dict) else None
        self._offers = [o for o in self._offers if o["document"] != document]
        await self._say()
        return self.state()


# ===== what the project needs, installed at once =====


class Install(Protocol):
    """Libraries installed into a Python, each line of the installer's output handed on as it comes
    (server/environments.py install)."""

    def __call__(
        self, python: str, specs: list[str], *, heard: Callable[[str], Awaitable[None]]
    ) -> Awaitable[tuple[int | None, str]]: ...


@dataclass(frozen=True)
class NeedSources:
    """What the needs are read from beside the project's own files (the composition root hands each in).

    connections  the names of the connections the open project uses (services/project_scope.py ProjectUse)
    blade_of     a connection's saved blade by its name (its code: the packages it imports)
    hooks        what an extension adds: hooks.project_code, the canvases' widgets as (why, code)
    touched      requirements.txt written: the code files' watch told
    """

    connections: Callable[[], list[str]] = lambda: []
    blade_of: Callable[[str], Blade] | None = None
    hooks: Hooks = field(default_factory=Hooks)
    touched: Callable[[str], Awaitable[Any]] | None = None


SAY_EVERY: float = 0.25  # the progress notice at most this often while no package changes its status
TYPE_WHY: str = "the project's type"
SETTLE_SECONDS: float = 2.0  # a saved code file looked at again once the saves have stopped this long
CODE_FILES: tuple[str, ...] = (".py", ".ipynb", "requirements.txt")


class ProjectInstalls:
    """Everything the open project needs, found as it opens and installed in one install (agent: on Allow).
    Its project and its Python are ProjectPython's (it is told when a project opens, or its `.venv` is made);
    the project's own code is read through that service's files (adapters/environment.py project_code)."""

    def __init__(
        self,
        python: ProjectPython,
        install: Install,
        approvals: Approvals,
        sources: NeedSources,
        changed: Callable[[], Awaitable[Any]] | None = None,
    ) -> None:
        self.ws = python.ws
        self._python = python
        self.files = python.files
        self._install = install
        self._approvals = approvals
        self._sources = sources
        self._changed = changed  # the Environment's Libraries follow
        self._folder: str | None = None
        self._state = needs_rules.State()
        self._task: asyncio.Task[None] | None = None
        self._said_at = 0.0
        self._settling: asyncio.TimerHandle | None = None
        python.installs = self

    # ===== what the screens and the agent read =====

    def state(self) -> dict[str, Any]:
        """The pass as the bar draws it; `kernel`: the project's Python session while it runs (Restart)."""
        return self._state.to_json() | {"kernel": self._python.session_kernel()}

    async def _say(self, force: bool = True) -> None:
        now = time.monotonic()
        if not force and now - self._said_at < SAY_EVERY:
            return
        self._said_at = now
        await self.ws.live.broadcast({"type": "project_installs"} | self.state())

    # ===== a project opened =====

    async def project_changed(self, folder: str | None, auto: bool, again: bool = False) -> None:
        """A project opened, was made or closed (`again`: the same project, its `.venv` just made): the state
        starts afresh; with `auto` (SWISSARMYBENCH_PROJECT_VENV not off) its needs are looked for and what is
        missing installed, in the background (never waited for)."""
        if folder == self._folder and not again:
            return
        self._folder = folder
        self._state = needs_rules.State(project=_name(folder))
        if folder is not None and auto and not self._busy():
            self._state.state = "checking"
            self._task = asyncio.ensure_future(self._pass(folder, install=True, who="app"))
        await self._say()

    def heard(self, message: dict[str, Any]) -> None:
        """A notice went to the pages (the live listeners): a code file of the open project saved or changed
        (a new import, requirements.txt) has its needs looked for again and what is missing installed, once
        the saves settle (the owner, 2026-11-24: not only as the project opens)."""
        path = message.get("path")
        folder = self._folder
        if message.get("type") != "file_changed" or folder is None or not isinstance(path, str):
            return
        if not path.endswith(CODE_FILES) or not project_paths.inside(path, folder):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._settling is not None:
            self._settling.cancel()
        self._settling = loop.call_later(SETTLE_SECONDS, self._again, folder)

    def _again(self, folder: str) -> None:
        self._settling = None
        if folder == self._folder and not self._busy() and self._python.auto():
            self._task = asyncio.ensure_future(self._pass(folder, install=True, who="app"))

    async def check(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Look again (installs nothing): the needs, and which the project's Python lacks."""
        folder = self._open_folder()
        if not self._busy():
            await self._pass(folder, install=False, who=who)
        return self.state()

    async def run(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Install what the project lacks, in one install (Try again after a failure). The agent's waits for
        the user's Allow. Answers once it has started: the `project_installs` notice says how it goes."""
        folder = self._open_folder()
        if self._busy():
            return self.state()
        if not self.files.python_of(folder)[1]:
            raise Conflict(
                "This project has no Python of its own yet: make it first (the Environment's Libraries tab)."
            )
        await self._approvals.allowed(
            who,
            subject="Project",
            action="install libraries",
            detail="Install every library the open project needs into its own Python (.venv), and add them "
            "to requirements.txt.",
            otherwise="nothing was installed",
        )
        self._state.state, self._state.problem = "checking", None
        await self._say()
        self._task = asyncio.ensure_future(self._pass(folder, install=True, who=who))
        return self.state()

    async def wait(self) -> None:
        """Until the pass under way has ended (tests, and the server's stop)."""
        if self._task is not None:
            await asyncio.wait([self._task])

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()

    def _open_folder(self) -> str:
        if self._folder is None:
            raise Conflict("What a project needs is a project's: open or make one first (Home).")
        return self._folder

    def _busy(self) -> bool:
        return self._task is not None and not self._task.done()

    # ===== the pass =====

    def _needs(self, folder: str) -> tuple[list[needs_rules.Need], str, bool]:
        """Off the loop: the needs the project's Python lacks, that Python, and whether it is its own."""
        files = self.files.project_code(folder)
        code = [
            needs_rules.Code(where, piece)
            for where, text in files
            for piece in needs_rules.code_of(where, text)
        ]
        code += [needs_rules.Code(why, text) for why, text in self._sources.hooks.project_code(folder)]
        found = needs_rules.needs(
            self.files.read_requirements(folder),
            [(spec, TYPE_WHY) for spec in self._python.type_requirements(folder)],
            code,
            connection_needs(self._sources.connections, self._sources.blade_of),
            needs_rules.local_modules(where for where, _ in files),
        )
        python, own = self.files.python_of(folder)
        return needs_rules.missing(found, self.files.installed(python)), python, own

    async def _pass(self, folder: str, install: bool, who: str) -> None:
        try:
            lacking, python, own = await asyncio.to_thread(self._needs, folder)
        except Exception as error:  # a source that cannot be read: said, nothing installed
            if folder == self._folder:
                self._state.state, self._state.problem = "failed", needs_rules.failure([], str(error), 1)
                await self._say()
            return
        if folder != self._folder:
            return
        self._state.packages, self._state.own = needs_rules.listed(lacking), own
        if not lacking or not own or not install:
            self._state.state = "none"
            await self._say()
            return
        self._state.state = "installing"
        await self._say()
        await self._installed(folder, python, lacking, who)

    async def _installed(self, folder: str, python: str, lacking: list[needs_rules.Need], who: str) -> None:
        specs = [n.package for n in lacking]
        lines: list[str] = []

        async def heard(line: str) -> None:
            lines.append(line)
            progress = needs_rules.read_progress(lines, specs)
            before = [p["status"] for p in self._state.packages]
            for package, need in zip(self._state.packages, lacking, strict=True):
                package["status"] = progress.statuses.get(need.key, package["status"])
            self._state.current, self._state.share = progress.current, progress.share
            if folder == self._folder:
                await self._say(force=before != [p["status"] for p in self._state.packages])

        try:
            code, out = await self._install(python, specs, heard=heard)
        except Exception as error:  # the tool is missing, the environment cannot be written
            code, out = 1, str(error)
        have = await asyncio.to_thread(self.files.installed, python)
        versions = {needs_rules.key(n): v for n, v in have.items()}
        done = {n.key for n in lacking if needs_rules.satisfied(n.spec, versions.get(n.key))}
        for package, need in zip(self._state.packages, lacking, strict=True):
            package["status"] = "installed" if need.key in done else "failed"
        written = needs_rules.to_write(lacking, done)
        if written:
            text = await asyncio.to_thread(self.files.read_requirements, folder)
            for name in written:
                text = requirements_rules.with_library(text, name)
            touched = self._sources.touched
            if await asyncio.to_thread(self.files.write_requirements, folder, text) and touched is not None:
                await touched(folder)
        failed = [n.name for n in lacking if n.key not in done]
        self.ws.audit.write(
            who, "project_installs_failed" if failed else "project_installs", ", ".join(specs)
        )
        if folder != self._folder:
            return
        self._state.written = written
        self._state.current, self._state.share = None, 1.0
        self._state.restart = bool(done) and self._python.session_kernel() is not None
        self._state.state = "failed" if failed else "done"
        self._state.problem = needs_rules.failure(failed, out, code) if failed else None
        await self._say()
        if self._changed is not None:
            await self._changed()


def connection_needs(
    names: Callable[[], list[str]], blade_of: Callable[[str], Blade] | None
) -> list[tuple[str, list[str]]]:
    """Each connection the open project uses with the pip packages its code imports (read with ast, never
    run): (why: "connection Sales (SQL Server)", [pip, ...]). One that cannot be read is left out."""
    out: list[tuple[str, list[str]]] = []
    if blade_of is None:
        return out
    for name in names():
        try:
            blade = blade_of(name)
            pips = [p.pip for p in blade_rules.needed(blade.code, lambda module: False)]
        except Exception:  # noqa: S112 (a connection that cannot be read adds nothing)
            continue
        label = connection_kinds.label_of(blade.template) or connection_kinds.label_of(blade.dialect)
        out.append((f"connection {name}" + (f" ({label})" if label else ""), pips))
    return out


def _name(folder: str | None) -> str:
    return folder.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] if folder else ""


def _same(one: str, other: str) -> bool:
    return one.replace("\\", "/").casefold() == other.replace("\\", "/").casefold()
