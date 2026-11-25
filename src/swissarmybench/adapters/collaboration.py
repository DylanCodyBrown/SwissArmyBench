"""Collaboration's files (services/collaboration.py; domain/collaboration.py the format): the project's
.sab/collaboration/ read and written (atomically, only when the bytes change), its files' stamps for the look
every few seconds, and the project's objects as `@` finds them and as a reference checks them (is it still
there, at which line)."""

from __future__ import annotations

import ast
import getpass
import json
import os
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

from swissarmybench.adapters.atomic_files import write_atomic
from swissarmybench.domain import collaboration as rules
from swissarmybench.domain import local_api

Stamp = tuple[int, int]
SKIPPED = {".venv", "__pycache__", "node_modules", "sandbox", "builds", "exports", ".ipynb_checkpoints"}
MOST_FILES = 400  # the project's files looked at for `@`
DEEPEST = 3  # folders below the project's top


class CollaborationFiles:
    def read(self, path: str) -> str | None:
        try:
            return Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def read_bytes(self, path: str) -> bytes | None:
        try:
            return Path(path).read_bytes()
        except OSError:
            return None

    def write(self, path: str, data: str | bytes) -> bool:
        return write_atomic(path, data, if_changed=True, newline="\n")

    def remove(self, path: str) -> None:
        Path(path).unlink(missing_ok=True)

    def exists(self, path: str) -> bool:
        return Path(path).exists()

    def stamps(self, folder: str) -> dict[str, Stamp]:
        """Every file under the folder (its path inside it, with / between parts): its time and size."""
        out: dict[str, Stamp] = {}
        root = Path(folder)
        if not root.is_dir():
            return out
        for path in root.rglob("*"):
            if path.name.startswith(".") or not path.is_file():
                continue  # an atomic write's temporary file
            try:
                stat = path.stat()
            except OSError:
                continue
            out[path.relative_to(root).as_posix()] = (stat.st_mtime_ns, stat.st_size)
        return out


def _project_files(folder: Path) -> Iterator[Path]:
    count = 0
    for top, dirs, files in os.walk(folder):
        here = Path(top)
        depth = len(here.relative_to(folder).parts)
        dirs[:] = sorted(d for d in dirs if d not in SKIPPED and not d.startswith(".") and depth < DEEPEST)
        for name in sorted(files):
            if name.endswith((".ipynb", ".py", ".sql", ".canvas.json")):
                count += 1
                if count > MOST_FILES:
                    return
                yield here / name


def _functions(code: str) -> dict[str, int]:
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return {}
    return {
        node.name: node.lineno
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    }


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


class ProjectObjects:
    """What `@` can point at in the open project, and whether a reference's object is still there."""

    def __init__(self, tables: Callable[[], Iterable[Any]], connections: Callable[[], Any]) -> None:
        # The open tables (the dataset store's, each with its columns) and the connections' listing.
        self._store = tables
        self._listing = connections

    def _tables(self) -> dict[str, list[str]]:
        return {i.name: [c.name for c in i.columns] for i in self._store()}

    def _connections(self) -> list[str]:
        return [str(c["name"]) for c in self._listing()["connections"]]

    def present(self, folder: str, ref: rules.Reference) -> tuple[bool, int | None]:
        """(there, its line): a file read only as far as the kind needs."""
        if ref.kind == "change":
            return True, None
        if ref.kind in ("table", "column"):
            columns = self._tables().get(ref.path)
            return columns is not None and (ref.kind == "table" or ref.id in columns), None
        if ref.kind == "connection":
            return ref.path in self._connections(), None
        path = Path(folder) / ref.path
        if not path.is_file():
            return False, None
        if ref.kind == "cell":
            notebook = _json(path)
            numbers = rules.cell_numbers(notebook) if isinstance(notebook, dict) else {}
            return ref.id.isdigit() and int(ref.id) in numbers, None
        if ref.kind == "function":
            line = _functions(path.read_text(encoding="utf-8", errors="replace")).get(ref.id)
            return line is not None, line
        if ref.kind == "endpoint":
            return self._endpoint(path, ref.id)
        if ref.kind == "widget":
            return ref.id in rules.widget_ids(_json(path)), None
        return True, None

    def _endpoint(self, path: Path, name: str) -> tuple[bool, int | None]:
        try:
            api = local_api.parse(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, SyntaxError):
            return False, None
        found = next((e for e in api.endpoints if e.name == name), None)
        return found is not None, found.line if found else None

    def candidates(self, folder: str | None) -> list[rules.Reference]:
        """Every object of the project `@` offers: its notebooks and their cells, scripts and their functions,
        .sql files, API.py's endpoints, canvas widgets, saved analyses, the open tables and their columns, the
        connections."""
        out: list[rules.Reference] = []
        for name, columns in sorted(self._tables().items()):
            out.append(rules.Reference("table", name, "", name))
            out += [rules.Reference("column", name, c, f"{name}.{c}") for c in columns]
        out += [rules.Reference("connection", n, "", n) for n in sorted(self._connections())]
        if not folder:
            return out
        root = Path(folder)
        for path in _project_files(root):
            out += self._of_file(root, path)
        for saved in sorted((root / ".sab" / "visualizations").glob("*.json")):
            out.append(rules.Reference("analysis", saved.relative_to(root).as_posix(), "", saved.stem))
        return out

    def _of_file(self, root: Path, path: Path) -> list[rules.Reference]:
        place = path.relative_to(root).as_posix()
        if path.name.endswith(".canvas.json"):
            widgets = rules.widget_ids(_json(path))
            return [rules.Reference("widget", place, i, f"{w} ({place})") for i, w in sorted(widgets.items())]
        if path.suffix == ".ipynb":
            notebook = _json(path)
            cells = rules.cell_numbers(notebook) if isinstance(notebook, dict) else {}
            return [
                rules.Reference("notebook", place, "", place),
                *(rules.Reference("cell", place, str(n), f"{place} cell {n}") for n in sorted(cells)),
            ]
        if path.suffix == ".sql":
            return [rules.Reference("sql", place, "", place)]
        text = path.read_text(encoding="utf-8", errors="replace")
        made = [rules.Reference("script", place, "", place)]
        made += [rules.Reference("function", place, n, f"{place} {n}()") for n in sorted(_functions(text))]
        if path.name == "API.py":
            try:
                endpoints = local_api.parse(text).endpoints
            except (ValueError, SyntaxError):
                endpoints = []
            made += [rules.Reference("endpoint", place, e.name, f"{e.method} {e.path}") for e in endpoints]
        return made


def system_name() -> str:
    """This computer's user name (a person's name until one is set)."""
    try:
        return getpass.getuser()
    except (OSError, KeyError):
        return "Someone"
