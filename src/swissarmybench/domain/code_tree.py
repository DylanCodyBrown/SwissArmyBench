"""The Files pane of the Notebooks and Scripts pages, on the right of the code since 2026-11-22 (the owner,
2026-11-21: "What it should have is a project file explorer to browse and open all project scripts" / "a by
module navigation tree on the left to navigate all of the scripts (except the notebooks)").

The Scripts page's tree: every .py of the project by module (`scripts/etl/load.py` is `etl.load`), in groups
(Your scripts, Project code: what the app makes and the pages), each module's outline by ast (classes, their
methods, functions, module constants); never a notebook. The Notebooks page's: the project's notebooks, one
list, data.ipynb first (every notebook a notebook: the owner, 2026-11-22, "we just have notebooks"). Pure
rules, no I/O: the files come in as (path inside the project, made, edited by hand).
"""

from __future__ import annotations

import ast
import posixpath
import re
from collections.abc import Iterable
from typing import Any

from swissarmybench.domain import project_paths, workbench_pages

# The groups in their order, each a folder of the tree.
SCRIPTS = "scripts"  # Your scripts: scripts/ and its packages
PROJECT = "project"  # Project code: data.py, the scaffold's modules, pages/*.py, the canvas's export
API = "api"  # Local sandbox API: API.py and its exports (exports/api/<target>/)
GROUP_WORDS: dict[str, str] = {SCRIPTS: "Your scripts", PROJECT: "Project code", API: "Local sandbox API"}
# What the app makes in a project, and from where (said in the tab's bar: "Made from data.ipynb").
_MADE_FROM: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^data\.py$"), "data.ipynb"),
    (re.compile(r"^pages/[^/]+\.py$"), "the app's canvas"),
    (re.compile(r"^exports/api/[^/]+/"), "API.py"),  # a local sandbox API's export (domain/api_targets.py)
    # The project scaffold's core files and the sandbox mirror (domain/scaffold.py MADE).
    (re.compile(r"^adapter\.py$"), "Swiss Army Bench's adapter"),
    (re.compile(r"^connections\.py$"), "the library's connections"),
    (re.compile(r"^sandbox_(data|connections)\.py$"), "the sandbox"),
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
    groups: dict[str, list[dict[str, Any]]] = {SCRIPTS: [], PROJECT: [], API: []}
    for relative, text in files:
        relative = relative.replace("\\", "/")
        if not relative.endswith(".py") or not listed(relative):
            continue
        group = (
            SCRIPTS
            if relative.startswith("scripts/")
            else API
            if relative == "API.py" or relative.startswith("exports/api/")
            else PROJECT
        )
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
    for key in (SCRIPTS, PROJECT, API):
        if key == API and not groups[API]:
            continue
        items = sorted(groups[key], key=lambda f: (f["folder"].casefold(), f["name"].casefold()))
        out.append({"id": key, "name": GROUP_WORDS[key], "files": items})
    return out


def notebook_tree(paths: Iterable[str]) -> list[dict[str, Any]]:
    """The Notebooks page's one group: every notebook, data.ipynb at the top first (the file data.py is made
    from; no kind of its own: the owner, 2026-11-22, "that concept is gone we just have notebooks")."""
    data: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    for relative in paths:
        relative = relative.replace("\\", "/")
        if not relative.lower().endswith(".ipynb") or not listed(relative):
            continue
        item = {"path": relative, "name": posixpath.basename(relative), "folder": posixpath.dirname(relative)}
        (data if relative.lower() == "data.ipynb" else rest).append(item)
    rest.sort(key=lambda f: (f["folder"].casefold(), f["name"].casefold()))
    return [{"id": "notebooks", "name": "Notebooks", "files": data + rest}]


STRUCTURES = "structures"


def structure_group(paths: Iterable[str]) -> dict[str, Any] | None:
    """Both pages' Structures group (2026-11-22, the owner: "I want it beside the ide so you can search and
    explore"): the project's JSON, YAML, XML and TOML files at its top and in its structures/ folder, each
    opening as a tab beside the code; never an app's canvas, a workbook design or the app's .sab/ state.
    None when there are none."""
    files = []
    for relative in paths:
        relative = relative.replace("\\", "/")
        if not workbench_pages.is_structure_path(relative) or not listed(relative):
            continue
        if "/" in relative and not relative.startswith("structures/"):
            continue
        name, folder = posixpath.basename(relative), posixpath.dirname(relative)
        files.append({"path": relative, "name": name, "folder": folder})
    if not files:
        return None
    files.sort(key=lambda f: (f["folder"].casefold(), f["name"].casefold()))
    return {"id": STRUCTURES, "name": "Structures", "files": files, "kind": "structure"}


# The library's code (the owner, 2026-11-21: "this is meant to expose the high level code of everything in the
# app for fine tuning"): its folders as groups of the Scripts page's tree; blades are the Blades pane's.
LIBRARY_GROUPS: tuple[tuple[str, str], ...] = (
    ("connections", "Connections"),
    ("apis", "APIs"),
    ("vaults", "Key vaults"),
    ("widgets", "Widgets"),
)


def library_tree(root: str | None, paths: Iterable[str]) -> list[dict[str, Any]]:
    """The library's .py files (whole paths under `root`) as groups: Connections, APIs, Key vaults, Widgets
    (the last once the library has the folder). Each file editable in place; the app reads it on its next
    use."""
    if not root:
        return []
    found: dict[str, list[dict[str, Any]]] = {key: [] for key, _ in LIBRARY_GROUPS}
    for full in paths:
        relative = project_paths.relative_in(full, root)
        if relative is None or not relative.endswith(".py") or not listed(relative):
            continue
        top = relative.split("/", 1)[0]
        if top not in found:
            continue
        name = posixpath.basename(relative)
        found[top].append(
            {
                "path": relative,
                "full": full,
                "name": name,
                "folder": posixpath.dirname(relative),
                "module": name[: -len(".blade.py")] if name.endswith(".blade.py") else name[: -len(".py")],
                "made_from": None,
                "edited": False,
                "read_only": False,
                "library": True,
                "outline": [],
            }
        )
    return [
        {
            "id": f"library-{key}",
            "name": words,
            "files": sorted(found[key], key=lambda f: f["path"].casefold()),
        }
        for key, words in LIBRARY_GROUPS
        if found[key] or key != "widgets"
    ]


def generated_group(tables: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """What the app generates, read-only, shown so it can be seen: each open table's transformations as one
    DuckDB query (its read-only cell's text), with Fine-tune as a script."""
    files = [
        {
            "path": f"{t['name']} (transformations)",
            "full": f"table:{t['name']}",
            "name": str(t["name"]),
            "folder": "",
            "module": str(t["name"]),
            "made_from": "its grid's steps",
            "edited": False,
            "read_only": True,
            "item": f"table:{t['name']}",
            "text": t.get("code") or "",
            "actions": [{"id": "fine-tune", "label": "Fine-tune as a script"}],
            "outline": [],
        }
        for t in tables
    ]
    return {"id": "generated", "name": "Generated (read-only)", "files": files}


def fine_tune_name(table: str, taken: Iterable[str]) -> str:
    """scripts/<table>_tuned.py, the first free name (a number after it when taken)."""
    stem = "".join(c if c.isalnum() or c == "_" else "_" for c in table.lower()).strip("_") or "table"
    used = {t.casefold() for t in taken}
    name, n = f"scripts/{stem}_tuned.py", 2
    while name.casefold() in used:
        name, n = f"scripts/{stem}_tuned_{n}.py", n + 1
    return name
