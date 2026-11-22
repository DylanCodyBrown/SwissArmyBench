"""One Python per project (the owner, 2026-11-21; Plans/environment.plan.md, step 4): the project's own
`.venv` at its top and the ONE session every notebook and script of the project runs in, as RStudio. Pure
rules: which document is the project's, what the `.venv` is made with, what a notebook's older environment
of its own offers the project, and every word the screens say about them.

  in_project      a document's path is inside the open project's folder (read from the text alone)
  venv_packages   what the project's `.venv` is made with: the kernel, the Excel readers, requirements.txt
  chosen          the libraries someone chose in an environment: the ones no other library there needs
  offered         a notebook's older environment: its chosen libraries the project does not have yet
  *_words         the one line said for each state (making, ready, failed, a session's Interrupt and Restart)
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from swissarmybench.domain import project_paths
from swissarmybench.domain.environments import ALWAYS, EXCEL

VENV: str = ".venv"
# What makes an environment run at all: never "chosen" by someone, never offered to a project.
MACHINERY: frozenset[str] = frozenset({"pip", "setuptools", "wheel", "ipykernel", "uv"})
MAX_OFFERED: int = 60
_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_REQUIREMENT = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9,._-]+\])?\s*([<>=!~]=?\s*[A-Za-z0-9.*+!-]+)?$"
)


def key(name: str) -> str:
    """A library's name as pip compares it (Scikit_Learn is scikit-learn)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def in_project(path: Any, folder: Any) -> bool:
    """Whether a document is the open project's: its path is inside the project's folder. Both are full
    paths as the app keeps them; nothing is read from disk. A path with `..` in it is never taken."""
    return project_paths.inside(path, folder)


def venv_packages(requirements_text: str, for_type: Sequence[str] = ()) -> list[str]:
    """What a project's `.venv` is made with: the kernel the app runs code in, the Excel readers, what the
    project's type needs (`for_type`: its contract's requirements, Streamlit for a canvas: 2026-11-22, so a
    project whose requirements.txt leaves it out still draws its widgets), then each library requirements.txt
    names (a line pip would not take from a list, an option or a path, is left for the user's own install;
    its own line for a library wins)."""
    wanted: list[str] = [*ALWAYS, *EXCEL, *for_type]
    for line in requirements_text.splitlines():
        text = line.split("#", 1)[0].strip()
        if text and _REQUIREMENT.match(text):
            wanted.append(re.sub(r"\s+", "", text))
    seen: dict[str, str] = {}
    for spec in wanted:
        found = _NAME.match(spec)
        if found:
            seen[key(found.group(1))] = spec  # requirements.txt's own line wins over the default
    return list(seen.values())


def chosen(requires: Mapping[str, Iterable[str]]) -> list[str]:
    """The libraries someone chose in an environment, from each installed library's own list of what it
    needs: the ones no other library there needs (pandas, not the numpy it brought), without the machinery
    that makes an environment run. Sorted by name."""
    needed: set[str] = set()
    for name, needs in requires.items():
        for need in needs:
            found = _NAME.match(need)
            if found and key(found.group(1)) != key(name):
                needed.add(key(found.group(1)))
    return sorted((n for n in requires if key(n) not in needed and key(n) not in MACHINERY), key=key)


def offered(chosen_there: Sequence[str], requirements_text: str, installed: Iterable[str]) -> list[str]:
    """What a notebook's older environment offers the project: its chosen libraries that requirements.txt
    does not name and the project's Python does not have."""
    named = set()
    for line in requirements_text.splitlines():
        found = _NAME.match(line.split("#", 1)[0])
        if found:
            named.add(key(found.group(1)))
    have = {key(n) for n in installed}
    return [n for n in chosen_there if key(n) not in named and key(n) not in have][:MAX_OFFERED]


def offer_words(document: str, libraries: Sequence[str]) -> str:
    """The one line said when a notebook that had its own environment opens in a project."""
    name = document.replace("\\", "/").rsplit("/", 1)[-1]
    start = f"{name} had its own environment. It now runs in the project's one Python"
    if not libraries:
        return f"{start}, which already has its libraries."
    shown = ", ".join(libraries[:4]) + (f" and {len(libraries) - 4:,} more" if len(libraries) > 4 else "")
    count = "1 library" if len(libraries) == 1 else f"{len(libraries):,} libraries"
    return f"{start}: add its {count} ({shown}) to the project?"


@dataclass(frozen=True)
class State:
    """The project's Python as the screens say it."""

    folder: str | None
    python: str
    own: bool  # the project's `.venv` (False: the app's own Python)
    making: bool = False
    problem: str | None = None

    @property
    def status(self) -> str:
        if self.folder is None:
            return "none"
        if self.making:
            return "making"
        if self.own:
            return "ready"
        return "failed" if self.problem else "missing"

    @property
    def words(self) -> str:
        return STATUS_WORDS[self.status]


STATUS_WORDS: dict[str, str] = {
    "none": "No project is open: each notebook and script runs in a Python session of its own.",
    "making": (
        "Making this project's Python (.venv in its folder). Your code runs in the app's own Python until "
        "it is ready."
    ),
    "ready": "This project has its own Python (.venv in its folder).",
    "missing": "This project has no Python of its own yet: your code runs in the app's own Python.",
    "failed": (
        "This project's Python (.venv) could not be made: your code runs in the app's own Python. Try again "
        "from the Environment's Libraries tab."
    ),
}
READY_WORDS: str = (
    "This project's Python (.venv) is ready. Restart the Python session to use it: every variable is cleared."
)
SESSION_WORDS: str = (
    "One Python session for the whole project: every notebook and script runs in it, one cell at a time, "
    "and sees the same variables. Interrupt stops what is running, whichever document started it; Restart "
    "clears every variable for all of them."
)
RESTARTED_WORDS: str = "The project's Python session was restarted: every variable is cleared."
STOPPED_WORDS: str = "The project's Python session stopped: every variable is gone. Run starts a new one."
FALLBACK_WORDS: str = (
    "This project's Python (.venv) does not run: the session started in the app's own Python instead."
)


def made_words(code: int | None, output: str) -> str | None:
    """Why the `.venv` could not be made (None: it was), with the last lines the tool printed."""
    if code == 0:
        return None
    if code is None:
        return "Making the project's Python took over 10 minutes and was stopped."
    tail = " ".join(output.strip().splitlines()[-3:])[:400]
    return f"Making the project's Python failed{': ' + tail if tail else '.'}"
