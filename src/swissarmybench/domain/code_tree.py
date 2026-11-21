"""The explorer on the left of the Notebooks and Scripts pages (the owner, 2026-11-21: "What it should have is
a project file explorer to browse and open all project scripts" / "a by module navigation tree on the left to
navigate all of the scripts (except the notebooks)").

The Scripts page's tree: every .py of the project by module (`scripts/etl/load.py` is `etl.load`), in groups
(Your scripts, Project code: what the app makes and the pages), each module's outline by ast (classes, their
methods, functions, module constants); never a notebook. The Notebooks page's: the project's notebooks, the
data notebook first. Pure rules, no I/O: the files come in as (path inside the project, made, edited by hand).
"""

from __future__ import annotations

import ast
import posixpath
import re
from collections.abc import Iterable
from typing import Any

# The groups in their order, each a folder of the tree.
SCRIPTS = "scripts"  # Your scripts: scripts/ and its packages
PROJECT = "project"  # Project code: data.py, the scaffold's modules, pages/*.py, the canvas's export
GROUP_WORDS: dict[str, str] = {SCRIPTS: "Your scripts", PROJECT: "Project code"}
# What the app makes in a project, and from where (said in the tab's bar: "Made from data.ipynb").
_MADE_FROM: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^data\.py$"), "data.ipynb"),
    (re.compile(r"^pages/[^/]+\.py$"), "the app's canvas"),
)
_SKIP = re.compile(r"(^|/)(\.[^/]*|__pycache__|\.venv|venv|node_modules|builds)(/|$)")
_CONSTANT = re.compile(r"^[A-Z][A-Z0-9_]*$")
MAX_SYMBOLS = 400


def made_from(relative: str) -> str | None:
    """What a made file is made from ("data.ipynb"), or None for a file of the user's."""
    for pattern, source in _MADE_FROM:
        if pattern.match(relative):
            return source
    return None


def module_name(relative: str) -> str:
    """A .py's module as Python imports it: scripts/ is the scripts' root (`scripts/etl/load.py` is
    `etl.load`), a package's `__init__.py` is the package, anything else from the project's top."""
    path = relative.replace("\\", "/")
    if path.startswith("scripts/"):
        path = path[len("scripts/") :]
    stem = path[: -len(".py")] if path.endswith(".py") else path
    parts = [p for p in stem.split("/") if p]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) or "scripts"


def listed(relative: str) -> bool:
    """A file the tree shows: not hidden, not a cache, an environment or a launch's build."""
    return not _SKIP.search(relative.replace("\\", "/"))


def outline(text: str) -> dict[str, Any]:
    """A module's symbols by ast, in their order: {"symbols": [{name, kind (class, function, method,
    constant), line, end, children}], "error": null or {line, message}} (a syntax error: no symbols; the page
    keeps the last outline it had)."""
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        return {"symbols": [], "error": {"line": error.lineno or 1, "message": error.msg}}
    symbols: list[dict[str, Any]] = []

    def symbol(
        node: ast.AST, name: str, kind: str, children: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        return {
            "name": name,
            "kind": kind,
            "line": getattr(node, "lineno", 1),
            "end": getattr(node, "end_lineno", None) or getattr(node, "lineno", 1),
            "children": children or [],
        }

    for node in tree.body:
        if len(symbols) >= MAX_SYMBOLS:
            break
        if isinstance(node, ast.ClassDef):
            methods = [
                symbol(m, m.name, "method")
                for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            symbols.append(symbol(node, node.name, "class", methods))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(symbol(node, node.name, "function"))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and _CONSTANT.match(target.id):
                    symbols.append(symbol(node, target.id, "constant"))
    return {"symbols": symbols, "error": None}


def script_tree(files: Iterable[tuple[str, str | None]], edited: Iterable[str] = ()) -> list[dict[str, Any]]:
    """The Scripts page's groups from the project's .py files ((path inside it, its text or None when not
    read)): Your scripts (scripts/ and its packages, folders kept), then Project code. Each file: path,
    name, module, made_from (a made file), edited (made but edited by hand), outline."""
    hand = set(edited)
    groups: dict[str, list[dict[str, Any]]] = {SCRIPTS: [], PROJECT: []}
    for relative, text in files:
        relative = relative.replace("\\", "/")
        if not relative.endswith(".py") or not listed(relative):
            continue
        group = SCRIPTS if relative.startswith("scripts/") else PROJECT
        source = made_from(relative)
        groups[group].append(
            {
                "path": relative,
                "name": posixpath.basename(relative),
                "folder": posixpath.dirname(relative),
                "module": module_name(relative),
                "made_from": source,
                "edited": bool(source) and relative in hand,
                "read_only": bool(source) and relative not in hand,
                "outline": outline(text)["symbols"] if text is not None else [],
            }
        )
    out = []
    for key in (SCRIPTS, PROJECT):
        items = sorted(groups[key], key=lambda f: (f["folder"].casefold(), f["name"].casefold()))
        out.append({"id": key, "name": GROUP_WORDS[key], "files": items})
    return out


def notebook_tree(paths: Iterable[str]) -> list[dict[str, Any]]:
    """The Notebooks page's groups: the data notebook (data.ipynb at the top) first, then the rest."""
    data: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    for relative in paths:
        relative = relative.replace("\\", "/")
        if not relative.lower().endswith(".ipynb") or not listed(relative):
            continue
        item = {"path": relative, "name": posixpath.basename(relative), "folder": posixpath.dirname(relative)}
        (data if relative.lower() == "data.ipynb" else rest).append(item)
    rest.sort(key=lambda f: (f["folder"].casefold(), f["name"].casefold()))
    return [
        {"id": "data", "name": "Data notebook", "files": data},
        {"id": "notebooks", "name": "Notebooks", "files": rest},
    ]
