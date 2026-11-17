"""The editors' intelligence at the edge: Jedi's project and environments, the project's modules read,
and the linters that may be there (pyflakes in the app's Python, Ruff in the document's environment,
DuckDB's own parser for a DuckDB SQL cell).

Nothing is written. Ruff reads the text from its standard input; DuckDB's parser runs on a connection
of its own that reads nothing (extract_statements parses, it never runs).
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

_RUFF_SECONDS = 3.0
_RUFF_AGAIN_SECONDS = 60.0
# The package's own folder: Jedi always finds `swissarmybench` (the kernel's `sab`).
_PACKAGE_ROOT = str(Path(__file__).resolve().parents[2])


class JediWorld:
    """Jedi's Project for a folder and Environment for a Python, each made once."""

    def __init__(self) -> None:
        self._projects: dict[tuple[str, tuple[str, ...]], Any] = {}
        self._environments: dict[str, Any] = {}
        self._lock = threading.Lock()

    def project(self, folder: str | None, extra: tuple[str, ...] = ()) -> Any:
        import jedi

        root = folder if folder and os.path.isdir(folder) else os.getcwd()
        key = (root, extra)
        with self._lock:
            if key not in self._projects:
                paths = [p for p in (root, *extra, _PACKAGE_ROOT) if os.path.isdir(p)]
                self._projects[key] = jedi.Project(
                    root, added_sys_path=paths, smart_sys_path=True, load_unsafe_extensions=False
                )
            return self._projects[key]

    def environment(self, python: str | None) -> Any:
        """The document's own Python's libraries (None: the app's)."""
        import jedi

        if not python or os.path.realpath(python) == os.path.realpath(sys.executable):
            return None
        with self._lock:
            if python not in self._environments:
                try:
                    self._environments[python] = jedi.create_environment(python, safe=False)
                except Exception:  # not a Python Jedi can read: the app's libraries instead
                    self._environments[python] = None
            return self._environments[python]


class ProjectModules:
    """The project's scaffold modules' sources, read again only when a file changed."""

    def __init__(self) -> None:
        self._read: dict[str, tuple[float, str]] = {}

    def sources(self, folder: str | None, modules: tuple[str, ...]) -> dict[str, str]:
        out: dict[str, str] = {}
        if not folder:
            return out
        for module in modules:
            path = os.path.join(folder, f"{module}.py")
            try:
                when = os.path.getmtime(path)
            except OSError:
                continue
            kept = self._read.get(path)
            if kept is None or kept[0] != when:
                try:
                    kept = (when, Path(path).read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    continue
                self._read[path] = kept
            out[module] = kept[1]
        return out


_PYFLAKES_CODES = {
    "UndefinedName": "F821",
    "UnusedImport": "F401",
    "UnusedVariable": "F841",
    "RedefinedWhileUnused": "F811",
    "FStringMissingPlaceholders": "F541",
    "ImportStarUsed": "F403",
    "ImportStarUsage": "F405",
}


class Linters:
    """pyflakes (when the app's Python has it), Ruff (when the document's environment has it) and
    DuckDB's parser."""

    def __init__(self, run_text: Callable[..., tuple[int, str] | None] | None = None) -> None:
        # Starting a process is server/'s (server/text_process.py run_text, handed in by bootstrap.py);
        # without one (a test's stand-in), no process runs and Ruff is simply not there.
        self._run: Callable[..., tuple[int, str] | None] = run_text or (lambda *a, **k: None)
        # Each Python's Ruff, and when it was looked for (one not there is looked for again a minute on:
        # it may have been installed since).
        self._ruff: dict[str, tuple[float, str | None]] = {}
        self._duck: Any = None
        self._duck_lock = threading.Lock()

    def pyflakes(self, text: str) -> list[dict[str, Any]] | None:
        """pyflakes's messages (None: not installed in the app's Python)."""
        try:
            from pyflakes import checker as flakes
        except ImportError:
            return None
        import ast

        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []
        out = []
        for m in flakes.Checker(tree, filename="<cell>").messages:
            kind = type(m).__name__
            name = str(m.message_args[0]) if m.message_args else ""
            out.append(
                {
                    "code": _PYFLAKES_CODES.get(kind, "F"),
                    "line": m.lineno,
                    "col": m.col + 1,
                    "name": name,
                    "message": m.message % m.message_args,
                }
            )
        return out

    def ruff_command(self, python: str | None) -> str | None:
        """Ruff beside the document's Python (its environment's), or its `ruff` package; None: not there."""
        python = python or sys.executable
        kept = self._ruff.get(python)
        if kept is not None and (kept[1] is not None or time.monotonic() - kept[0] < _RUFF_AGAIN_SECONDS):
            return kept[1]
        found: str | None = None
        folder = os.path.dirname(python)
        for name in ("ruff", "ruff.exe"):
            candidate = os.path.join(folder, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                found = candidate
                break
        if found is None and os.path.isfile(python):
            answer = self._run(
                [python, "-I", "-c", "from ruff.__main__ import find_ruff_bin; print(find_ruff_bin())"],
                timeout=10,
            )
            path = answer[1].strip() if answer else ""
            found = path if answer and answer[0] == 0 and path and os.path.isfile(path) else None
        self._ruff[python] = (time.monotonic(), found)
        return found

    def ruff(self, text: str, command: str, folder: str | None) -> list[dict[str, Any]] | None:
        """Ruff's diagnostics on the text: the folder's own Ruff settings apply (the project's, else the
        document's folder's); with no folder, Ruff's defaults (never the server's own working folder's).
        None: it failed."""
        cwd = folder if folder and os.path.isdir(folder) else None
        own = [] if cwd else ["--isolated"]
        answer = self._run(
            [
                *(command, "check", "--output-format", "json", "--no-cache", "--exit-zero"),
                *own,
                *("--stdin-filename", "cell.py", "-"),
            ],
            stdin=text,
            timeout=_RUFF_SECONDS,
            cwd=cwd,
        )
        if answer is None:
            return None
        try:
            found = json.loads(answer[1] or "[]")
        except ValueError:
            return None
        return found if isinstance(found, list) else None

    def duckdb_error(self, sql: str) -> str | None:
        """DuckDB's parser on the text: its error message, or None when it parses."""
        import duckdb

        with self._duck_lock:
            if self._duck is None:
                self._duck = duckdb.connect(":memory:")
                self._duck.execute("SET enable_external_access = false")
                self._duck.execute("SET lock_configuration = true")
            try:
                self._duck.extract_statements(sql)
            except duckdb.Error as error:
                return str(error)
        return None
