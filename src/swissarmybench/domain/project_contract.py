"""The project contract (Plans/adapter.plan.md "The project contract is the extension's, as JSON"):
contract.json.

The owner, 2026-11-22: "A project's contract is laid out in json. Everything including the ide language. The
back end always remains python based with the duckdb adapter being the entry for data and apis in and out."
Each extension that adds a project type carries one `contract.json` at its root (a packaged extension's
package folder, a folder extension's own folder); one with no project type (Copilot, Git) has none. It says
what a type of project is; a project's own state stays `.sab/project.json`.

The file, FORMAT 1 (every key but format, type, name and deliverable may be left out):

    {
      "format": 1,
      "type": "inventory",                 the project type it adds (a project's .sab/project.json names it)
      "name": "Inventory",                 the type's name (New project, the Project Explorer's cards)
      "deliverable": "an inventory report", what a project of this type hands over, in words
      "languages": {"*.py": "python", "*.md": "markdown"},   the IDE's language per file pattern
      "cells": ["python", "sql"],          the cell kinds its notebooks offer
      "files": [                           the deliverable: files and folders (a path ending in /) it adds
        {"path": "report.md", "owner": "user", "about": "the report", "starter": "# {name}\\n"}
      ],
      "requirements": ["openpyxl>=3.1"],   lines for the project's requirements.txt
      "canvas": null,                      its canvas kind, or none
      "export": ["report"],                what its Export makes, by name
      "areas": [],                         the rail's areas open in it (none: all)
      "words": {"title", "for_whom", "explain", "example"}   the Project Explorer's words for beginners
    }

A file's `owner` is "user" (the user's own, written once by New project) or "app" (made by the app;
`made_from` says from what, `grows_on` on which events it grows, `section` the marker of one grown part).
`starter` is the text New project writes for it, `{name}` the project's name; a path may hold `{slug}` (the
project's name as a file name) where it is named after the project. The core files (adapter.py,
connections.py, API.py, data.py, data.ipynb, requirements.txt) are the base's in every type: a contract adds
to them, never names one. Any type may deliver an Excel workbook beside its own deliverable
(Plans/excel.plan.md): a file whose path ends .xlsx or .xlsm (`workbooks/{slug}.xlsx`, made by sab_excel
from a workbook.py: owner app, made_from, grows_on) is declared like any other; it is made, so it has no
starter.

`check(raw)` is the one checker: it reads a contract loosely where nothing is lost and refuses, in one
sentence naming the key, what would be (an unknown key, a newer format, a path out of the project, a core
file). Standard library only.
"""

from __future__ import annotations

import json
import re
from typing import Any

FORMAT = 1
FILE = "contract.json"
# The base's own files in every project type: a contract never names one (it adds, never replaces).
CORE_FILES: frozenset[str] = frozenset(
    {"adapter.py", "connections.py", "API.py", "data.py", "data.ipynb", "requirements.txt"}
)
# Cell kinds every project has: the rest of a contract's cells are its extra cell kinds (a mode's cell_kinds).
BASE_CELLS: frozenset[str] = frozenset({"python", "sql", "dax", "html", "markdown"})
OWNERS: tuple[str, ...] = ("user", "app")
WORKBOOKS: tuple[str, ...] = (".xlsx", ".xlsm")  # an Excel workbook: a file any type may deliver
WORDS: tuple[str, ...] = ("title", "for_whom", "explain", "example")
_KEYS = frozenset(
    {
        "format",
        "type",
        "name",
        "deliverable",
        "languages",
        "cells",
        "files",
        "requirements",
        "canvas",
        "export",
    }
    | {"areas", "words", "core"}
)
_FILE_KEYS = frozenset({"path", "owner", "about", "starter", "made_from", "grows_on", "section"})
_WORD = re.compile(r"[a-z][a-z0-9_.+-]{0,39}")
_PATTERN = re.compile(r"[A-Za-z0-9_.*?/{}\[\]-]{1,80}")
_REQUIREMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\-\[\],<>=!~ ;\"'()]{0,199}")
MAX_FILES = 50
MAX_STARTER = 200_000


class ContractError(ValueError):
    """A contract.json that is not one: its one sentence names the key."""


def _text(raw: Any, key: str, *, required: bool = False, limit: int = 300) -> str:
    if raw is None and not required:
        return ""
    if not isinstance(raw, str) or (required and not raw.strip()):
        raise ContractError(f"contract.json: {key} is {'required as ' if required else ''}text.")
    if len(raw) > limit:
        raise ContractError(f"contract.json: {key} is longer than {limit} characters.")
    return raw.strip()


def _word(raw: Any, key: str) -> str:
    if not isinstance(raw, str) or not _WORD.fullmatch(raw.strip().lower()):
        raise ContractError(
            f"contract.json: {key} {raw!r} is not a name "
            "(lower-case letters, digits, _ . + -; a letter first)."
        )
    return raw.strip().lower()


def _words(raw: Any, key: str) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ContractError(f"contract.json: {key} is a list of names.")
    return list(dict.fromkeys(_word(v, key) for v in raw))


def _path(raw: Any, key: str) -> str:
    """A path inside the project: relative, forward slashes, no `..`, never a core file."""
    text = _text(raw, key, required=True, limit=200).replace("\\", "/")
    parts = text.rstrip("/").split("/")
    if text.startswith("/") or ":" in text or any(p in ("", ".", "..") for p in parts):
        raise ContractError(f"contract.json: {key} {text!r} is not a path inside the project.")
    if text in CORE_FILES:
        raise ContractError(
            f"contract.json: {key} {text!r} is a core file of every project: the base makes it."
        )
    return text


def _file(raw: Any, at: int) -> dict[str, Any]:
    key = f"files[{at}]"
    if not isinstance(raw, dict):
        raise ContractError(f"contract.json: {key} is an object with a path.")
    unknown = sorted(set(raw) - _FILE_KEYS)
    if unknown:
        raise ContractError(f"contract.json: {key} has a key it does not know: {unknown[0]}.")
    path = _path(raw.get("path"), f"{key}.path")
    owner = raw.get("owner", "user")
    if owner not in OWNERS:
        raise ContractError(f"contract.json: {key}.owner is user or app.")
    starter = raw.get("starter")
    if starter is not None and (not isinstance(starter, str) or len(starter) > MAX_STARTER):
        raise ContractError(f"contract.json: {key}.starter is the file's text.")
    if starter is not None and path.endswith("/"):
        raise ContractError(f"contract.json: {key} is a folder: it has no starter text.")
    if starter is not None and is_workbook(path):
        raise ContractError(
            f"contract.json: {key} is an Excel workbook: it is made (sab_excel.build), "
            "so it has no starter text."
        )
    made_from = raw.get("made_from")
    return {
        "path": path,
        "owner": owner,
        "about": _text(raw.get("about"), f"{key}.about"),
        "starter": starter,
        "made_from": None if made_from is None else _text(made_from, f"{key}.made_from"),
        "grows_on": _words(raw.get("grows_on"), f"{key}.grows_on"),
        "section": _text(raw.get("section"), f"{key}.section"),
    }


def _languages(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ContractError('contract.json: languages is {"<file pattern>": "<language>"}.')
    out: dict[str, str] = {}
    for pattern, language in raw.items():
        if not isinstance(pattern, str) or not _PATTERN.fullmatch(pattern):
            raise ContractError(f"contract.json: languages has a pattern that is not one: {pattern!r}.")
        out[pattern] = _word(language, f"languages[{pattern!r}]")
    return out


def _requirements(raw: Any) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(r, str) and _REQUIREMENT.fullmatch(r) for r in raw):
        raise ContractError("contract.json: requirements is a list of lines as pip reads them.")
    return list(dict.fromkeys(r.strip() for r in raw))


def check(raw: Any) -> dict[str, Any]:
    """The contract, every key filled in its one shape; ContractError names what is wrong."""
    if not isinstance(raw, dict):
        raise ContractError("contract.json is one JSON object.")
    version = raw.get("format")
    if not isinstance(version, int) or isinstance(version, bool):
        raise ContractError(f"contract.json: format is a number ({FORMAT}).")
    if version > FORMAT:
        raise ContractError(
            f"contract.json is format {version}, made for a newer Swiss Army Bench (this one reads {FORMAT})."
        )
    unknown = sorted(set(raw) - _KEYS)
    if unknown:
        raise ContractError(f"contract.json has a key it does not know: {unknown[0]}.")
    if raw.get("core", "base") != "base":
        raise ContractError("contract.json: core is base (the core files are always the base's).")
    files = raw.get("files") or []
    if not isinstance(files, list) or len(files) > MAX_FILES:
        raise ContractError(f"contract.json: files is a list of at most {MAX_FILES}.")
    checked = [_file(f, i) for i, f in enumerate(files)]
    paths = [f["path"] for f in checked]
    if len(set(paths)) != len(paths):
        raise ContractError("contract.json: a path is in files twice.")
    words = raw.get("words") or {}
    if not isinstance(words, dict):
        raise ContractError("contract.json: words is an object (title, for_whom, explain, example).")
    canvas = raw.get("canvas")
    return {
        "format": FORMAT,
        "type": _word(raw.get("type"), "type"),
        "name": _text(raw.get("name"), "name", required=True, limit=60),
        "deliverable": _text(raw.get("deliverable"), "deliverable", required=True, limit=120),
        "core": "base",
        "languages": _languages(raw.get("languages")),
        "cells": _words(raw.get("cells"), "cells"),
        "files": checked,
        "requirements": _requirements(raw.get("requirements")),
        "canvas": None if canvas is None else _word(canvas, "canvas"),
        "export": _words(raw.get("export"), "export"),
        "areas": _words(raw.get("areas"), "areas"),
        "words": {k: _text(words.get(k), f"words.{k}", limit=600) for k in WORDS},
    }


def read(text: str) -> dict[str, Any]:
    """contract.json's text, checked (broken JSON said with its line)."""
    try:
        raw = json.loads(text)
    except ValueError as error:
        line = getattr(error, "lineno", None)
        raise ContractError(f"contract.json is not JSON{f' (line {line})' if line else ''}.") from None
    return check(raw)


def write(contract: dict[str, Any]) -> str:
    """A contract as its file's text: two-space JSON, keys in the order above, one newline at the end."""
    return json.dumps(check(contract), indent=2, ensure_ascii=False) + "\n"


# ===== what the base reads from a contract =====


def languages(contract: dict[str, Any]) -> list[str]:
    """The IDE's languages, each once, in the order the patterns name them (python when none is named)."""
    return list(dict.fromkeys(contract["languages"].values())) or ["python"]


def is_workbook(path: str) -> bool:
    """Is this path an Excel workbook's (.xlsx, .xlsm)?"""
    return path.lower().endswith(WORKBOOKS)


def workbooks(contract: dict[str, Any]) -> list[str]:
    """The Excel workbooks the type delivers (beside its own deliverable), as the contract lists them."""
    return [f["path"] for f in contract["files"] if is_workbook(f["path"])]


def deliverable_files(contract: dict[str, Any]) -> list[str]:
    """The deliverable's paths, as the contract lists them."""
    return [f["path"] for f in contract["files"]]


def slug(name: str) -> str:
    """The project's name as a file name: lower case, words joined by _."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "project"


def scaffold(contract: dict[str, Any], name: str) -> dict[str, Any]:
    """New project's own files from the contract (a type with no scaffold of its own): each file with a
    starter, its {name} the project's; a folder gets a README.md saying what it is for. The same shape an
    extension's scaffold answers: {"app": False, "files": {path: text}, "requirements": [...]}."""
    files: dict[str, str] = {}
    for entry in contract["files"]:
        path = entry["path"].replace("{slug}", slug(name))
        if path.endswith("/"):
            files[f"{path}README.md"] = f"{entry['about'] or path.rstrip('/')}\n"
        elif entry["starter"] is not None:
            files[path] = entry["starter"].replace("{name}", name)
    return {"app": False, "files": files, "requirements": list(contract["requirements"])}


def as_mode(contract: dict[str, Any]) -> dict[str, Any]:
    """The contract as a project type's mode (extensions.py's MODE fields), for an extension that declares no
    MODE of its own."""
    return {
        "type": contract["type"],
        "name": contract["name"],
        "deliverable": contract["deliverable"],
        "canvases": [contract["canvas"]] if contract["canvas"] else [],
        "languages": languages(contract),
        "cell_kinds": [c for c in contract["cells"] if c not in BASE_CELLS],
        "export": list(contract["export"]),
        "areas": list(contract["areas"]),
        **contract["words"],
    }


def matches(path: str, listed: str) -> bool:
    """Is `path` (a file New project wrote) the contract's `listed` path: the same, inside a listed folder, or
    the listed path with {slug} standing for any name."""
    if listed.endswith("/"):
        return path.startswith(listed.replace("{slug}", "")) if "{slug}" not in listed else False
    pattern = re.escape(listed).replace(re.escape("{slug}"), r"[a-z0-9_]+")
    return re.fullmatch(pattern, path) is not None
