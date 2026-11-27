"""The Scripts IDE at the edge: Jedi's go to definition, references and rename over the project (the same Jedi
Project the editors' intelligence uses: adapters/intellisense.py JediWorld), the project's code files read and
written (atomically, only when the text changes), Ruff's format in the document's own Python.
"""

from __future__ import annotations

import sysconfig
from collections.abc import Callable
from pathlib import Path
from typing import Any

from swissarmybench.adapters.atomic_files import write_atomic

_FORMAT_SECONDS = 8.0
MAX_FILE = 2_000_000


def _place(name: Any, root: str | None) -> dict[str, Any]:
    path = str(name.module_path) if name.module_path else None
    inside = bool(path and root and Path(path).resolve().is_relative_to(Path(root).resolve()))
    return {
        "path": path,
        "line": name.line,
        "column": (name.column or 0) + 1,
        "name": name.name,
        "module": name.module_name,
        "kind": name.type,
        "in_project": inside,
        "builtin": bool(name.in_builtin_module()),
        "description": name.description,
    }


def python_roots() -> tuple[str, ...]:
    """Python's own folders (the standard library, site-packages): a library's source is shown read-only."""
    paths = sysconfig.get_paths()
    return tuple(
        dict.fromkeys(p for k in ("stdlib", "platstdlib", "purelib", "platlib") if (p := paths.get(k)))
    )


class ScriptCode:
    """Jedi's answers for a file of the project, and the files themselves."""

    def __init__(self, run_text: Callable[..., tuple[int, str] | None] | None = None) -> None:
        self._run: Callable[..., tuple[int, str] | None] = run_text or (lambda *a, **k: None)

    @staticmethod
    def _script(text: str, path: str | None, project: Any) -> Any:
        import jedi

        return jedi.Script(text, path=path, project=project)

    def definition(
        self, text: str, line: int, column: int, path: str | None, project: Any, root: str | None
    ) -> list[dict[str, Any]]:
        """Where the name at (line, column from 1) is defined: followed through imports."""
        names = self._script(text, path, project).goto(line, column - 1, follow_imports=True)
        return [_place(n, root) for n in names if n.line is not None]

    def references(
        self, text: str, line: int, column: int, path: str | None, project: Any, root: str | None
    ) -> list[dict[str, Any]]:
        names = self._script(text, path, project).get_references(line, column - 1, scope="project")
        return [_place(n, root) for n in names if n.line is not None]

    def rename(
        self, text: str, line: int, column: int, path: str | None, project: Any, new_name: str
    ) -> dict[str, str]:
        """The files a rename changes: {path: its new text} (nothing written here)."""
        refactoring = self._script(text, path, project).rename(line, column - 1, new_name=new_name)
        return {str(p): changed.get_new_code() for p, changed in refactoring.get_changed_files().items()}

    @staticmethod
    def read(path: str) -> str:
        found = Path(path)
        if found.stat().st_size > MAX_FILE:
            raise ValueError(f"{found.name} is over {MAX_FILE // 1_000_000} MB: not opened here.")
        return found.read_text(encoding="utf-8")

    @staticmethod
    def write(path: str, text: str) -> bool:
        """The text to its file (a unique temporary file, then one replace); False when it was the same."""
        return bool(write_atomic(path, text, if_changed=True, newline=""))

    @staticmethod
    def exists(path: str) -> bool:
        return Path(path).exists()

    @staticmethod
    def is_folder(path: str) -> bool:
        return Path(path).is_dir()

    @staticmethod
    def move(source: str, target: str) -> None:
        """A file or folder moved (renamed) within the project: refused when the target is there."""
        to = Path(target)
        if to.exists():
            raise FileExistsError(f"{to.name} is there already.")
        to.parent.mkdir(parents=True, exist_ok=True)
        Path(source).rename(to)

    @staticmethod
    def make_package(folder: str) -> str:
        """A package: its folder and an empty __init__.py; the __init__.py's path."""
        root = Path(folder)
        if root.exists():
            raise FileExistsError(f"{root.name} is there already.")
        root.mkdir(parents=True)
        init = root / "__init__.py"
        write_atomic(init, "", newline="")
        return str(init)

    def format(self, text: str, ruff: str, folder: str | None) -> str | None:
        """Ruff's format of the text (its project's settings), or None when it failed (a syntax error)."""
        cwd = folder if folder and Path(folder).is_dir() else None
        answer = self._run(
            [ruff, "format", *([] if cwd else ["--isolated"]), "--stdin-filename", "script.py", "-"],
            stdin=text,
            timeout=_FORMAT_SECONDS,
            cwd=cwd,
        )
        if answer is None or answer[0] != 0:
            return None
        return answer[1]
