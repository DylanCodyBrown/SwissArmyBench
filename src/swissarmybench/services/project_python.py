"""One Python per project (the owner, 2026-11-21; Plans/environment.plan.md, step 4; rules in
domain/project_python.py): the project's own `.venv` at its top, made by the app on New project and on
opening a project that has none (in the background: the page is never held, and the app's own Python runs
the code until it is ready), and what a notebook's older environment of its own offers the project.

The one session every document of the project runs in is the Workbench's (services/workbench.py asks
`session()` here for the folder and the Python); this service ends it when the project changes.

Notices: `project_python` {status, words, said?} when the making starts, ends or fails, and when a
notebook's older environment was read (its one line).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from swissarmybench.domain import project_python as rules
from swissarmybench.services.workspace import Conflict, Workspace


class Files(Protocol):
    """The project's Python as files (adapters/environment.py): nothing runs."""

    def python_of(self, folder: str | None) -> tuple[str, bool]: ...

    def read_requirements(self, folder: str) -> str: ...

    def installed(self, python: str) -> dict[str, str]: ...

    def requires(self, python: str) -> dict[str, list[str]]: ...


Make = Callable[[str, list[str]], Awaitable[tuple[int | None, str]]]


class ProjectPython:
    def __init__(self, ws: Workspace, files: Files, make: Make, enabled: bool = True) -> None:
        self.ws = ws
        self._files = files
        self._make = make
        self._enabled = enabled  # off: no `.venv` is made by itself (tests; SWISSARMYBENCH_PROJECT_VENV=off)
        self._folder: str | None = None
        self._making: dict[str, asyncio.Task[None]] = {}  # by project folder
        self._problems: dict[str, str] = {}
        self._offers: list[dict[str, Any]] = []  # notebooks' older environments, read once (memory only)
        # The Workbench's part, handed over by the composition root: the project's session ended, and a
        # document's remembered environment forgotten once it was read.
        self.end_session: Callable[[], Awaitable[Any]] | None = None
        self.session_kernel: Callable[[], str | None] = lambda: None
        self.forget_environment: Callable[[str], None] | None = None
        # What the project's type needs in its `.venv` beyond requirements.txt (extensions.requirements_of:
        # Streamlit for a canvas), by the project's folder.
        self.type_requirements: Callable[[str], list[str]] = lambda folder: []

    # ===== what the screens and the Workbench read =====

    def _state(self) -> rules.State:
        folder = self._folder
        python, own = self._files.python_of(folder)
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
        return self._folder, self._files.python_of(self._folder)[0]

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
        if folder is not None and self._enabled and not self._files.python_of(folder)[1]:
            self._start(folder)
            await self._say(rules.STATUS_WORDS["making"])
        else:
            await self._say()  # the pages follow the project: its Python, its one session

    def _start(self, folder: str) -> None:
        if folder in self._making:
            return
        self._problems.pop(folder, None)
        task = asyncio.ensure_future(self._run(folder))
        self._making[folder] = task

    async def _run(self, folder: str) -> None:
        try:
            text = await asyncio.to_thread(self._files.read_requirements, folder)
            code, out = await self._make(folder, rules.venv_packages(text, self.type_requirements(folder)))
            problem = rules.made_words(code, out)
            if problem is None and not self._files.python_of(folder)[1]:
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

    async def make(self, body: Any = None, who: str = "user") -> dict[str, Any]:
        """Make the project's `.venv` now (Try again after a failure, or a project opened while the making
        was switched off). Answers at once: the `project_python` notice says when it is ready."""
        folder = self._folder
        if folder is None:
            raise Conflict("A Python of its own is a project's: open or make one first (Home).")
        if self._files.python_of(folder)[1]:
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

    # ===== a notebook that had its own environment =====

    def moved(self, path: str, python: str) -> dict[str, Any] | None:
        """A document of the project opened with a Python remembered for it alone (a per-notebook
        environment from before): read once. Its chosen libraries the project lacks are offered for
        requirements.txt, the document's own choice is forgotten, and one line says so. None: nothing to say
        (it was the project's own Python)."""
        folder = self._folder
        if folder is None:
            return None
        project_python, _ = self._files.python_of(folder)
        # The project's own Python, or the app's own, is no environment of the notebook's: nothing to offer.
        if _same(python, project_python) or _same(python, self._files.python_of(None)[0]):
            if self.forget_environment is not None:
                self.forget_environment(path)
            return None
        try:
            there = rules.chosen(self._files.requires(python))
            libraries = rules.offered(
                there, self._files.read_requirements(folder), self._files.installed(project_python)
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


def _same(one: str, other: str) -> bool:
    return one.replace("\\", "/").casefold() == other.replace("\\", "/").casefold()
