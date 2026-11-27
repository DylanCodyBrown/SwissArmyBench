"""Folder extensions' rules (Plans/folder-extensions.plan.md; the owner, 2026-11-21: "Extensions should be
loadable as a folder in the app so users can create them with their own agents as needed and transform the
app").

A folder extension is the library's `extensions/<id>/`, trusted like the rest of the library: it loads at
start without asking, as blades do. Its folder has the shape of a packaged extension's package, so one moves
between the two:

    library/extensions/inventory/
      extension.py    the same module values a packaged extension has (ID, NAME, ADDS, MODE, AREAS, routes,
                      commands, STARTERS...), and REQUIRES: the packages it needs in the app's Python
      commands.py     its agent commands (the golden rule)
      contract.json   when it adds a project type (domain/project_contract.py)
      README.md       what it adds

It loads as the package `sab_ext_<id>` (its folder that package's only path: its own files import each other
as `.commands`, never as top-level modules). Its REQUIRES are a literal list read before it loads: a missing
one is offered through the one missing-package prompt (Install now), never installed by itself. Remove moves
its folder to the trash (the user's own; the agent's on Allow). Here: its id, REQUIRES, a load error's one
sentence, the words, and New extension's folder. Standard library only.
"""

from __future__ import annotations

import ast
import re
from typing import Any

from swissarmybench.domain import project_contract

FOLDER: str = "extensions"  # the library's folder of them: library/extensions/<id>/
MODULE_PREFIX: str = "sab_ext_"  # each loads as the package sab_ext_<id>
# Its id names its module, its routes (/<id>/...) and its commands' prefix (<id>_...): a Python name.
_ID = re.compile(r"[a-z][a-z0-9_]{1,30}")
# The base's own first path segments and areas a folder extension's id would collide with.
RESERVED_IDS: frozenset[str] = frozenset(
    {
        "app", "api", "apis", "blades", "catalog", "cards", "connections", "data", "desktop", "environment",
        "explorer", "extensions", "folders", "grids", "health", "library", "lifecycle", "notebooks",
        "project", "projects", "sandbox", "scripts", "session", "settings", "static", "structures", "team",
        "variables", "workbench", "workspace", "ws", "sab", "swissarmybench",
    }
)  # fmt: skip


class FolderError(ValueError):
    """A folder extension's id or New extension's request that is not one: one sentence."""


def is_id(value: str) -> bool:
    """Is a folder's name a folder extension's id (anything else in library/extensions/ is left alone)."""
    return bool(_ID.fullmatch(value))


def check_id(value: object, taken: set[str]) -> str:
    """A new folder extension's id: a Python name (its module, routes and commands), never the base's own word
    nor an extension's that exists (`taken`: the catalog's and the ones found)."""
    if not isinstance(value, str) or not value.strip():
        raise FolderError('Send {"id": "<the new extension\'s id>"}: lower case, such as inventory.')
    text = value.strip().lower()
    if not _ID.fullmatch(text):
        raise FolderError(
            f"{value!r} is not a folder extension's id: 2 to 31 lower-case letters, digits and _, "
            "a letter first."
        )
    if text in RESERVED_IDS:
        raise FolderError(f"{text} is a word of Swiss Army Bench's own: choose another id.")
    if text in taken:
        raise FolderError(f"There is an extension {text} already: choose another id.")
    return text


# The manifest's values read without running extension.py: its card before it loads (or when it cannot).
MANIFEST: tuple[str, ...] = ("ID", "NAME", "VERSION", "DESCRIPTION", "ADDS", "REQUIRES")


def literals(source: str) -> dict[str, Any]:
    """extension.py's top-level manifest values that are literals (MANIFEST), read with ast, never run."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    out: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign):
            targets: list[ast.expr] = [node.target]
        elif isinstance(node, ast.Assign):
            targets = list(node.targets)
        else:
            continue
        names = [t.id for t in targets if isinstance(t, ast.Name) and t.id in MANIFEST]
        if node.value is None or not names:
            continue
        try:
            value = ast.literal_eval(node.value)
        except ValueError:
            continue
        out |= dict.fromkeys(names, value)
    return out


def requires_of(source: str) -> list[str]:
    """extension.py's REQUIRES (a literal list of pip lines): what it needs before it can load. Anything else
    (none, or not a literal list of text): nothing."""
    value = literals(source).get("REQUIRES")
    return [v.strip() for v in value if isinstance(v, str) and v.strip()] if isinstance(value, list) else []


def dist_name(requirement: str) -> str:
    """A pip line's distribution: "openpyxl>=3.1" -> "openpyxl", "psycopg[binary]" -> "psycopg"."""
    return re.split(r"[\s\[<>=!~;(]", requirement.strip(), maxsplit=1)[0]


def _relative(filename: str, folder: str) -> str | None:
    return filename[len(folder) :].lstrip("/\\") if filename.startswith(folder) else None


def load_error(error: BaseException, folder: str) -> str:
    """A folder that did not load, in one sentence: what went wrong and the line in its own files."""
    line = ""
    trace = error.__traceback__
    while trace is not None:
        name = _relative(trace.tb_frame.f_code.co_filename, folder)
        if name is not None:
            line = f" ({name}, line {trace.tb_lineno})"
        trace = trace.tb_next
    if isinstance(error, SyntaxError) and error.filename:
        name = _relative(error.filename, folder)
        if name is not None:
            line = f" ({name}, line {error.lineno})"
    text = str(error).strip()
    words = text.splitlines()[0][:300] if text else ""
    return f"It did not load: {type(error).__name__}{f': {words}' if words else ''}{line}."


def wrong_id(declared: str, folder_name: str) -> str:
    return f"It did not load: extension.py's ID {declared!r} is not its folder's name {folder_name!r}."


def shadowed(ident: str) -> str:
    return f"The folder {ident} in the library is not loaded: {ident} is built in, and that wins."


def remove_question(name: str, path: str) -> str:
    return f"{name}'s folder goes to the trash: {path}. Its pages and commands stop now."


# ===== New extension: a working skeleton to grow =====


def scaffold(ident: str, name: str, project_type: str | None = None) -> dict[str, str]:
    """New extension's folder (relative path -> text): extension.py with one route, commands.py with one
    command, README.md, and contract.json when it adds a project type (one deliverable file)."""
    words = " ".join(name.split())[:60] or ident
    adds = [f"Its status: GET /{ident}/status and the agent's {ident}_status"]
    files: dict[str, str] = {}
    if project_type:
        contract = _contract(project_type, words)
        files[project_contract.FILE] = project_contract.write(contract)
        adds.append(f"The {words} project type")
    files["extension.py"] = _fill(_EXTENSION_PY, ident, words).replace("__ADDS__", repr(adds))
    files["commands.py"] = _fill(_COMMANDS_PY, ident, words)
    files["README.md"] = _fill(_README, ident, words)
    return files


def _contract(project_type: str, words: str) -> dict[str, Any]:
    kind = project_contract.check(
        {"format": 1, "type": project_type, "name": words, "deliverable": f"a {words} report"}
    )["type"]
    return {
        "format": 1,
        "type": kind,
        "name": words,
        "deliverable": f"a {words} report",
        "languages": {"*.py": "python", "*.ipynb": "python", "*.md": "markdown"},
        "cells": ["python", "sql"],
        "files": [
            {
                "path": f"{kind}.md",
                "owner": "user",
                "about": f"The {words} report this project hands over.",
                "starter": "# {name}\n\nWhat this project hands over, written here.\n",
            }
        ],
        "export": [kind],
        "words": {
            "title": words,
            "for_whom": f"For anyone making a {words} report.",
            "explain": f"Tables in data.ipynb, the analysis in notebooks, and {kind}.md as its report.",
            "example": "",
        },
    }


def _fill(template: str, ident: str, name: str) -> str:
    return template.replace("__ID__", ident).replace("__NAME__", name.replace('"', "'"))


_EXTENSION_PY = '''"""__NAME__: a folder extension of Swiss Army Bench (the library's extensions/__ID__/).

It is laid out in the order the app reads it:
  the manifest   ID, NAME, VERSION, DESCRIPTION, ADDS (its card on the Extensions page), REQUIRES (the
                 packages it needs in the app's Python: a missing one is offered with Install now, never
                 installed by itself), AREAS (its commands' prefix)
  routes         its routes under /__ID__/, given the base's seams (its composition root)
  commands       its agent commands, in commands.py (the golden rule: every action is the agent's too)
Its project type, when it adds one, is contract.json's: New project writes the files it lists.
The back end is Python only: never a .ts, .tsx, .css or .html file here (the front end draws what this says).
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

# ===== the manifest =====

ID = "__ID__"
NAME = "__NAME__"
VERSION = "0.1.0"
DESCRIPTION = "__NAME__, made as a folder extension."
ADDS = __ADDS__
# The packages it needs in the app's Python, as pip names them (a literal list: it is read before this loads).
REQUIRES: list[str] = []
# Its commands' area: their prefix and what they cover.
AREAS = (("__ID__", "__NAME__: its status"),)


def describe() -> dict[str, Any]:
    return {"id": ID, "name": NAME, "description": DESCRIPTION, "version": VERSION, "adds": ADDS}


# ===== routes: the composition root =====


def routes(seams: Any) -> list[BaseRoute]:
    """Its routes, under /__ID__/. Take what it needs from `seams` (settings, ws.audit, connections...): what
    the base offers an extension (swissarmybench.services.hooks Seams)."""

    async def status(request: Request) -> JSONResponse:
        return JSONResponse({"id": ID, "name": NAME, "ok": True})

    return [Route("/__ID__/status", status)]


# ===== commands: the agent's =====


def commands() -> dict[str, Any]:
    from .commands import COMMANDS

    return COMMANDS
'''

_COMMANDS_PY = '''"""__NAME__'s agent commands (the golden rule: each action the user has, the agent has)."""

from __future__ import annotations

from typing import Any

from swissarmybench.cli import api
from swissarmybench.cli.commands import Command, Registrar

COMMANDS: dict[str, Command] = {}
command = Registrar(COMMANDS)


@command("__ID___status", "__NAME__'s status")
def __ID___status(a: dict[str, Any]) -> Any:
    return api.call("GET", "/__ID__/status")
'''

_README = """# __NAME__

A folder extension of Swiss Army Bench: this folder is the library's `extensions/__ID__/`, found when the app
starts.

- `extension.py`: the manifest (ID, NAME, ADDS, REQUIRES, AREAS), `routes(seams)` and `commands()`.
- `commands.py`: its agent commands, each named `__ID___<verb>`.
- `contract.json` (when it adds a project type): its project type, deliverable files and IDE languages.

Grow it as the agent's guide says (`guide(topic="extensions")`). It travels with the library (a team's Git
repository too) and is trusted like the library's blades.
"""
