"""Making a notebook's own environment (the Workbench's New environment): a virtual environment with
the kernel and the libraries chosen, made with uv when this computer has it (fast, and it fetches any
Python version), else Python's own venv and pip. Each step's output is handed on line by line."""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

_STEP_SECONDS: float = 900.0


def python_in(folder: Path) -> Path:
    """The environment's own Python."""
    return folder / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def beside(folder: str) -> str | None:
    """A .venv (or venv) in the document's folder, when there is one."""
    for name in (".venv", "venv"):
        candidate = python_in(Path(folder) / name)
        if candidate.is_file():
            return str(candidate)
    return None


async def _step(command: list[str]) -> AsyncIterator[dict[str, Any]]:
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    if process.stdout is None:  # never: stdout was asked for as a pipe
        return
    try:
        async with asyncio.timeout(_STEP_SECONDS):
            while line := await process.stdout.readline():
                yield {"line": line.decode("utf-8", "replace").rstrip()}
            await process.wait()
    except TimeoutError:
        process.kill()
        yield {
            "failed": f"{Path(command[0]).name} took over {_STEP_SECONDS / 60:.0f} minutes and was stopped."
        }
        return
    if process.returncode != 0:
        shown = " ".join(Path(c).name if i == 0 else c for i, c in enumerate(command[:3]))
        yield {"failed": f"{shown} … ended with code {process.returncode}: see the lines above."}


async def create(folder: str, version: str | None, packages: list[str]) -> AsyncIterator[dict[str, Any]]:
    """Make the environment; its progress, then {"done": {"ok", "python" | "error"}}."""
    target = Path(folder).expanduser().resolve()
    if target.exists():
        yield {
            "done": {
                "ok": False,
                "error": f"{target} is already there: pick a new folder, or choose its Python.",
            }
        }
        return
    if not target.parent.is_dir():
        yield {"done": {"ok": False, "error": f"The folder {target.parent} is not there."}}
        return
    python = python_in(target)
    uv = shutil.which("uv")
    if uv:
        steps = [
            [uv, "venv", str(target), "--python", version or sys.executable, "--seed"],
            [uv, "pip", "install", "--python", str(python), *packages],
        ]
    elif version and version != f"{sys.version_info.major}.{sys.version_info.minor}":
        needs = f"Python {version} needs uv here (it fetches Python versions), or pick this app's own."
        yield {"done": {"ok": False, "error": needs}}
        return
    else:
        steps = [
            [sys.executable, "-m", "venv", str(target)],
            [str(python), "-m", "pip", "install", *packages],
        ]
    for command in steps:
        yield {"line": f"$ {' '.join(Path(c).name if i == 0 else c for i, c in enumerate(command))}"}
        async for event in _step(command):
            if "failed" in event:
                yield {"done": {"ok": False, "error": event["failed"]}}
                return
            yield event
    yield {"done": {"ok": True, "python": str(python)}}


# ===== the project's environment: its libraries (the Environment page's Libraries tab) =====

_CHANGE_SECONDS: float = 600.0
# Tests only: a script run in uv's and pip's place (the made-up installs of tests/libraries_standin.py).
STANDIN = "SWISSARMYBENCH_LIBRARIES_STANDIN"


def _uv() -> str | None:
    return shutil.which("uv") or next(
        (
            str(p)
            for p in (Path.home() / ".local" / "bin" / "uv", Path.home() / ".cargo" / "bin" / "uv")
            if p.is_file()
        ),
        None,
    )


async def _run(command: list[str]) -> tuple[int | None, str]:
    """A command's exit code (None: over ten minutes, stopped) and what it printed."""
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    try:
        out, _ = await asyncio.wait_for(process.communicate(), _CHANGE_SECONDS)
    except TimeoutError:
        process.kill()
        await process.wait()
        return None, ""
    return process.returncode, out.decode("utf-8", "replace")


async def install(python: str, specs: list[str], upgrade: bool = False) -> tuple[int | None, str]:
    """Install (or, with `upgrade`, update) libraries into `python`'s environment: uv when it is here,
    else that Python's pip."""
    more = ["--upgrade"] if upgrade else []
    standin = os.environ.get(STANDIN)
    if standin:  # tests only: uv and pip stood in for (tests/libraries_standin.py)
        return await _run([sys.executable, standin, "install", python, *more, *specs])
    uv = _uv()
    if uv:
        return await _run([uv, "pip", "install", "--python", python, *more, *specs])
    return await _run([python, "-m", "pip", "install", *more, *specs])


async def uninstall(python: str, names: list[str]) -> tuple[int | None, str]:
    standin = os.environ.get(STANDIN)
    if standin:
        return await _run([sys.executable, standin, "uninstall", python, *names])
    uv = _uv()
    if uv:
        return await _run([uv, "pip", "uninstall", "--python", python, *names])
    return await _run([python, "-m", "pip", "uninstall", "-y", *names])


async def make_venv(folder: str, packages: list[str]) -> tuple[int | None, str]:
    """A project's `.venv` at its top, with the kernel and the libraries its requirements.txt names."""
    target = Path(folder) / ".venv"
    python = python_in(target)
    uv = _uv()
    made = (
        [uv, "venv", str(target), "--python", sys.executable, "--seed"]
        if uv
        else [sys.executable, "-m", "venv", str(target)]
    )
    code, out = await _run(made)
    if code != 0 or not packages:
        return code, out
    code, more = await install(str(python), packages)
    return code, out + more


_client_copy: list[str] = []


def client_path() -> str:
    """A folder holding a copy of this package for a kernel's import path, so `import swissarmybench`
    (sab.*, %%sql cells, tables as grids) works in an environment that does not have it installed. The
    client needs only the standard library; the page's files are left out. Made once per server."""
    if not _client_copy:
        import tempfile

        package = Path(__file__).resolve().parents[1]
        holder = Path(tempfile.mkdtemp(prefix="swissarmybench-client-"))
        shutil.copytree(
            package,
            holder / "swissarmybench",
            ignore=shutil.ignore_patterns("web_static", "__pycache__", "*.pyc"),
        )
        _client_copy.append(str(holder))
    return _client_copy[0]


class ProjectLibraries:
    """The Environment's libraries port (services/environment.py): the project's Python and requirements.txt
    as files (`files`: adapters/environment.py, handed over by the composition root), its installs as
    processes (above)."""

    def __init__(self, files: Any) -> None:
        self.python_of = files.python_of
        self.version_of = files.version_of
        self.installed = files.installed
        self.read_requirements = files.read_requirements
        self.write_requirements = files.write_requirements
        self.latest = files.latest

    async def install(self, python: str, specs: list[str], upgrade: bool = False) -> tuple[int | None, str]:
        return await install(python, specs, upgrade)

    async def uninstall(self, python: str, names: list[str]) -> tuple[int | None, str]:
        return await uninstall(python, names)
