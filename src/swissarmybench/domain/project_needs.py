"""What a project needs installed, found as it opens and installed at once (the owner, 2026-11-23: "when a
project opens, auto detect all the installs needed and install them all at once with a informative progress
bar"). Pure rules: nothing is run, nothing is read from disk here.

  code_of        a document's code: a notebook's code cells (IPython's lines made Python), or a script's text
  local_modules  the project's own module names (its .py files and the folders that hold them)
  needs          every pip package the project needs and why: requirements.txt, the type, the app's own
                 machinery, the imports of its code, its connections' and its canvases' packages
  missing        the needs its Python does not meet (not there, or a pin in requirements.txt not met)
  read_progress  an install's own output lines (uv's or pip's) as each package's status
  State          the `project_installs` notice: checking, installing, done, failed or none, and its words
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain import refusals
from swissarmybench.domain.cell_facts import modules
from swissarmybench.domain.environments import ALWAYS, EXCEL
from swissarmybench.domain.intellisense import to_python
from swissarmybench.domain.packages import pip_name, provided
from swissarmybench.domain.updates import try_version

# What the app's own machinery needs (the kernel, the Excel readers): installed when missing, never written
# to requirements.txt (the app adds them to every project's Python by itself).
MACHINERY: dict[str, str] = {
    **{name: "Swiss Army Bench runs your code with it" for name in ALWAYS},
    **{name: "Swiss Army Bench reads Excel files with it" for name in EXCEL},
}
# Folders whose code is not the project's own (its Python, the app's state, made builds and exports).
SKIPPED_FOLDERS: frozenset[str] = frozenset(
    {".venv", "venv", ".sab", "builds", "exports", "sandbox", "__pycache__", "node_modules", ".git"}
)
MAX_FILES: int = 2_000
MAX_BYTES: int = 1_000_000  # a file over this is not read for its imports
MAX_WHY: int = 6  # the places said for one package
TAIL_LINES: int = 15  # an install's last lines kept as a failure's details
STATES: tuple[str, ...] = ("checking", "installing", "done", "failed", "none")
STATUSES: tuple[str, ...] = ("waiting", "installing", "installed", "failed")

_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_SPEC = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(\[[A-Za-z0-9,._-]+\])?\s*((?:[<>=!~]=?\s*[A-Za-z0-9.*+!-]+\s*,?\s*)*)$"
)
_TOP = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def key(name: str) -> str:
    """A library's name as pip compares it (Scikit_Learn is scikit-learn), extras left off."""
    found = _NAME.match(name)
    return re.sub(r"[-_.]+", "-", found.group(1) if found else name.strip()).lower()


def name_of(spec: str) -> str:
    found = _NAME.match(spec)
    return found.group(1) if found else spec.strip()


# ===== the project's code =====


def code_of(path: str, text: str) -> list[str]:
    """A document's Python: a notebook's code cells (a cell magic's cell left out, IPython's own lines made
    Python), or a script's whole text. A notebook that does not read gives nothing."""
    if not path.lower().endswith(".ipynb"):
        return [text]
    try:
        data = json.loads(text)
    except ValueError:
        return []
    cells = data.get("cells") if isinstance(data, dict) else None
    out = []
    for cell in cells if isinstance(cells, list) else []:
        if not isinstance(cell, dict) or cell.get("cell_type") != "code":
            continue
        source = cell.get("source")
        code = "".join(source) if isinstance(source, list) else str(source or "")
        if code.lstrip().startswith("%%"):
            continue  # %%sql, %%html, %%dax: not Python
        out.append(to_python(code))
    return out


def imports_in(code: str) -> list[str]:
    """The modules a piece of code imports (absolute imports only), read with ast; code that does not parse
    imports nothing."""
    try:
        return modules(ast.parse(code))
    except (SyntaxError, ValueError, RecursionError):
        return []


def local_modules(paths: Iterable[str]) -> set[str]:
    """The project's own module names from its files' paths (relative, forward slashes): each .py's stem and
    every folder that holds code, so `import etl` from scripts/etl/load.py is never taken for a library."""
    found: set[str] = set()
    for path in paths:
        parts = path.replace("\\", "/").split("/")
        stem = parts[-1].split(".", 1)[0]
        if parts[-1].lower().endswith(".py"):
            found.add(stem)
        found.update(parts[:-1])
    return found


def package_of(module: str, local: set[str]) -> str | None:
    """The pip package an import needs, or None: the standard library's, the app's own, the project's own
    module, or a name that does not look like a library's top-level module."""
    top = module.split(".", 1)[0]
    if provided(module) or top in local or not _TOP.match(top):
        return None
    pip, _ = pip_name(module)
    return pip


# ===== the needs =====


@dataclass
class Need:
    package: str  # what is installed: "pandas", "polars==1.36.0" (requirements.txt's own line)
    why: list[str] = field(default_factory=list)
    written: bool = False  # requirements.txt already names it
    machinery: bool = (
        False  # the app's own (the kernel, the Excel readers): never written to requirements.txt
    )

    @property
    def name(self) -> str:
        return name_of(self.package)

    @property
    def key(self) -> str:
        return key(self.package)

    @property
    def spec(self) -> str:
        """Its version rule ("==1.36.0", ">=2"), "" for any."""
        found = _SPEC.match(self.package)
        return re.sub(r"\s+", "", found.group(3)) if found and found.group(3) else ""


@dataclass(frozen=True)
class Code:
    """A piece of the project's code: where it is said to be (data.ipynb, scripts/load.py) and its text."""

    where: str
    text: str


def requirement_lines(text: str) -> list[str]:
    """requirements.txt's libraries as pip takes them from a list (comments, options and paths left out)."""
    out = []
    for line in text.splitlines():
        spec = line.split("#", 1)[0].strip()
        if spec and not spec.startswith("-") and _SPEC.match(spec):
            out.append(re.sub(r"\s+", "", spec))
    return out


def needs(
    requirements_text: str,
    for_type: Sequence[tuple[str, str]] = (),
    code: Sequence[Code] = (),
    packages: Sequence[tuple[str, Sequence[str]]] = (),
    local: set[str] | None = None,
) -> list[Need]:
    """Every package the project needs, each once (by pip's name), with why: requirements.txt's lines (its
    own line wins: a pin is kept), the app's machinery, the type's (spec, why), each import of its code, and
    the packages of what it uses (why, [pip, ...]): its connections, its canvases' widgets."""
    found: dict[str, Need] = {}
    own = local or set()

    def add(spec: str, why: str, written: bool = False, machinery: bool = False) -> None:
        need = found.get(key(spec))
        if need is None:
            need = found[key(spec)] = Need(spec, written=written, machinery=machinery)
        elif written and not need.written:
            need.package, need.written = spec, True
        need.machinery = need.machinery and machinery
        if why not in need.why:
            need.why.append(why)

    for spec in requirement_lines(requirements_text):
        add(spec, "requirements.txt", written=True)
    for name, why in MACHINERY.items():
        add(name, why, machinery=True)
    for spec, why in for_type:
        add(spec, why)
    for piece in code:
        for module in imports_in(piece.text):
            pip = package_of(module, own)
            if pip:
                add(pip, piece.where)
    for why, pips in packages:
        for pip in pips:
            if pip:
                add(pip, why)
    for need in found.values():
        need.why = need.why[:MAX_WHY]
    return list(found.values())


def satisfied(spec: str, version: str | None) -> bool:
    """Whether an installed version meets a requirement's rule (==, !=, >=, <=, >, <, ~=); a version or a rule
    that does not read counts as met (pip's own install is the judge then)."""
    if version is None:
        return False
    have = try_version(version)
    for part in [p for p in spec.split(",") if p]:
        found = re.fullmatch(r"(==|!=|>=|<=|~=|>|<)(.+)", part.strip())
        if not found or have is None:
            continue
        op, text = found.groups()
        if "*" in text:
            prefix = text.split("*", 1)[0].rstrip(".")
            same = version == prefix or version.startswith(prefix + ".")
            if (op == "==") != same:
                return False
            continue
        there = try_version(text)
        if there is None:
            continue
        ok = {
            "==": have == there,
            "!=": have != there,
            ">=": have >= there,
            "<=": have <= there,
            ">": have > there,
            "<": have < there,
            "~=": have >= there,
        }[op]
        if not ok:
            return False
    return True


def missing(found: Sequence[Need], installed: Mapping[str, str]) -> list[Need]:
    """The needs the project's Python does not meet: not installed, or installed at a version that
    requirements.txt's own rule does not take."""
    have = {key(name): version for name, version in installed.items()}
    return [n for n in found if not satisfied(n.spec, have.get(n.key))]


# ===== an install's progress, read from its own lines =====

_UV_PLUS = re.compile(r"^\s*\+\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_UV_BUSY = re.compile(
    r"^\s*(?:Downloading|Downloaded|Building|Built|Preparing)\s+([A-Za-z0-9][A-Za-z0-9._-]*)"
)
_COUNTED = re.compile(r"^\s*(Resolved|Prepared|Installed|Audited)\s+(\d+)\s+packages?", re.I)
_COLLECTING = re.compile(r"^\s*Collecting\s+([A-Za-z0-9][A-Za-z0-9._-]*)")
_PIP_DOWNLOADING = re.compile(r"^\s*Downloading\s+(?:\S+/)?([A-Za-z0-9][A-Za-z0-9._]*?)-\d")
_SATISFIED = re.compile(r"^\s*Requirement already satisfied:\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_INSTALLING = re.compile(r"^\s*Installing collected packages:\s*(.+)$")
_SUCCESS = re.compile(r"^\s*Successfully installed\s+(.+)$")


@dataclass(frozen=True)
class Progress:
    """Each package's status as the installer's output says it, the one it is busy with, and how far it is
    (0 to 1: a package busy counts half, one installed whole)."""

    statuses: dict[str, str]  # by key: waiting | installing | installed
    current: str | None
    phase: str  # starting | resolving | downloading | installing | finished
    share: float


def _without_version(word: str) -> str:
    """pip's `pandas-2.3.3` as pandas (the last dash that a digit follows)."""
    found = re.match(r"^(.+?)-\d", word)
    return found.group(1) if found else word


def read_progress(lines: Sequence[str], packages: Sequence[str]) -> Progress:
    """What an install's output lines say so far, for the packages asked for (pip names, or specs); a library
    pulled in only as another's dependency is not counted. uv: "Resolved N packages", "Downloading name",
    "Prepared N packages", "Installed N packages", " + name==version"; pip: "Collecting name", "Downloading
    name-version...", "Installing collected packages: ...", "Successfully installed name-version ..."."""
    names = {key(p): name_of(p) for p in packages}
    statuses = dict.fromkeys(names, "waiting")
    current: str | None = None
    phase = "starting"

    def busy(word: str) -> None:
        nonlocal current
        k = key(word)
        if k in statuses:
            current = names[k]
            if statuses[k] == "waiting":
                statuses[k] = "installing"

    def done(word: str) -> None:
        k = key(word)
        if k in statuses:
            statuses[k] = "installed"

    for line in lines:
        counted = _COUNTED.match(line)
        if counted:
            word = counted.group(1).lower()
            phase = {"resolved": "downloading", "prepared": "installing"}.get(word, "finished")
            if word == "audited":  # uv: everything was already there
                for k in statuses:
                    statuses[k] = "installed"
            continue
        if (found := _UV_PLUS.match(line)) is not None:
            done(found.group(1))
        elif (found := _SATISFIED.match(line)) is not None:
            done(found.group(1))
        elif (found := _COLLECTING.match(line)) is not None:
            phase = "downloading" if phase == "starting" else phase
            busy(found.group(1))
        elif (found := _PIP_DOWNLOADING.match(line)) is not None:
            phase = "downloading"
            busy(found.group(1))
        elif (found := _UV_BUSY.match(line)) is not None:
            phase = "downloading" if phase in ("starting", "resolving") else phase
            busy(found.group(1))
        elif (found := _INSTALLING.match(line)) is not None:
            phase = "installing"
            for word in found.group(1).split(","):
                busy(word.strip())
        elif (found := _SUCCESS.match(line)) is not None:
            phase = "finished"
            for word in found.group(1).split():
                done(_without_version(word))
        elif line.strip().lower().startswith(("resolving", "using python")) and phase == "starting":
            phase = "resolving"
    if current is not None and statuses.get(key(current)) == "installed":
        waiting = [names[k] for k, s in statuses.items() if s == "installing"]
        current = waiting[0] if waiting else None
    total = len(statuses)
    worth = {"waiting": 0.0, "installing": 0.5, "installed": 1.0}
    share = sum(worth[s] for s in statuses.values()) / total if total else 1.0
    return Progress(statuses, current, phase, round(share, 3))


# ===== the notice =====


@dataclass
class State:
    """The `project_installs` notice, whole each time: the pass's state, its packages and its words."""

    state: str = "none"
    project: str = ""  # the project's name, as the bar says it
    packages: list[dict[str, Any]] = field(default_factory=list)  # {name, why, status}
    current: str | None = None
    share: float = 0.0
    problem: dict[str, Any] | None = None
    written: list[str] = field(default_factory=list)  # what was added to requirements.txt
    restart: bool = False  # a Python session runs on the libraries as they were: Restart (asked) to use them
    own: bool = True  # the project has its own Python (.venv): nothing is installed into the app's own

    @property
    def total(self) -> int:
        return len(self.packages)

    @property
    def done(self) -> int:
        return sum(1 for p in self.packages if p["status"] == "installed")

    @property
    def words(self) -> str:
        return state_words(self)

    def to_json(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "project": self.project,
            "total": self.total,
            "done": self.done,
            "current": self.current,
            "share": self.share,
            "packages": [dict(p) for p in self.packages],
            "words": self.words,
            "problem": self.problem,
            "written": list(self.written),
            "restart": self.restart,
            "own": self.own,
        }


def listed(found: Sequence[Need], status: str = "waiting") -> list[dict[str, Any]]:
    """The notice's packages: each one's name, why it is needed (one short line), its status."""
    return [{"name": n.name, "why": why_words(n.why), "status": status} for n in found]


def why_words(places: Sequence[str]) -> str:
    """Why a package is needed, in one short line: "data.ipynb, scripts/load.py and 2 more"."""
    if not places:
        return ""
    if len(places) <= 2:
        return " and ".join(places)
    return f"{places[0]}, {places[1]} and {len(places) - 2:,} more"


def _libraries(n: int) -> str:
    return "1 library" if n == 1 else f"{n:,} libraries"


def state_words(state: State) -> str:
    """The bar's one line for each state."""
    setting_up = f"Setting up {state.project}" if state.project else "Setting up this project"
    if state.state == "checking":
        return f"{setting_up}: looking for what it needs…"
    if state.state == "installing":
        shown = f"installing {min(state.done + 1, state.total):,} of {state.total:,}"
        return f"{setting_up}: {shown}" + (f" · {state.current}" if state.current else "")
    if state.state == "done":
        written = " · added to requirements.txt" if state.written else ""
        restart = " · restart the Python session to use them" if state.restart else ""
        return f"Installed {_libraries(state.done)}{written}{restart}"
    if state.state == "failed":
        failed = [p["name"] for p in state.packages if p["status"] == "failed"]
        return (
            f"{_libraries(len(failed))} could not be installed ({', '.join(failed[:4])})"
            + (f"; {_libraries(state.done)} installed" if state.done else "")
            if failed
            else "The install failed."
        )
    if state.packages and not state.own:
        return (
            f"This project needs {_libraries(state.total)}: they go into its own Python (.venv), which is "
            "not made yet."
        )
    if state.packages:
        return f"This project needs {_libraries(state.total)} its Python does not have yet: Install them."
    return "Everything this project needs is installed."


def failure(failed: Sequence[str], output: str, code: int | None) -> dict[str, Any]:
    """A failed install in the one refusal shape: which ones, Try again, the installer's last lines."""
    tail = "\n".join(output.strip().splitlines()[-TAIL_LINES:])
    what = (
        "The install took over 10 minutes and was stopped."
        if code is None
        else f"These could not be installed: {', '.join(failed)}."
        if failed
        else "The install failed."
    )
    return refusals.shape(what, where="requirements", fixes=[refusals.try_again()], details=tail or None)


def to_write(found: Sequence[Need], installed_keys: set[str]) -> list[str]:
    """What an install adds to requirements.txt: each installed need it does not name yet, by name (the app's
    own machinery left out)."""
    return [n.name for n in found if n.key in installed_keys and not n.written and not n.machinery]
