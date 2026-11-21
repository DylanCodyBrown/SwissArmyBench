"""What belongs to the open project (the owner, 2026-11-16: "now objects are project scoped any notebooks
scripts or apps will have to be imported from another project"). Pure rules, no I/O.

  app data    the project's own definitions beside its files, in its working folder's `.sab/` folder: its
              connections and blades (`.sab/blades/<name>.json`, the
              blade store's own files: names, code and where each password comes from, never a value)
              and its saved Visualizations dashboards (`.sab/dashboards/<name>.json`)
  documents   the project's notebooks, scripts and apps: its files by their ending, the made ones marked
              (data.py and pages/*.py are exports of data.ipynb and the canvas); a notebook's role: the
              data notebook (data.ipynb), one an app's canvas links a cell of, or a plain one (each has an
              icon of its own, 2026-11-16)
  import      a copy into the project: a document from another project (its folder) or a
              loose file, a connection or blade from another project or from this computer's saved ones.
              A name the project has already is never overwritten: a document gets the next free name
              ("analysis 2.ipynb"), a connection or blade is skipped and said
  passwords   a connection is resolved on each computer: a password it asks for comes from this
              computer's keyring, an environment variable or a vault; none of those here is "needs a
              password", with the fix (never a dead end)
"""

from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from swissarmybench.domain import connections, notebooks, structures

APP_FOLDER: str = ".sab"
BLADES: str = f"{APP_FOLDER}/blades"
DASHBOARDS: str = f"{APP_FOLDER}/visualizations"  # the saved dashboards (.sab/dashboards before 2026-11-17)
OLD_DASHBOARDS: str = f"{APP_FOLDER}/dashboards"
KINDS: tuple[str, ...] = ("notebook", "script", "app", "structure")  # a structure: structures/<name>.json
MAX_IMPORT: int = 200  # documents, connections or blades in one import
# The project's own files the app writes from others: shown, marked, never imported on their own.
_MADE = re.compile(r"^(data\.py|pages/[^/]+\.py)$")
_FILE_NAME = re.compile(r"[^/]+\.json")


class ScopeError(ValueError):
    """A request about the project's scope that cannot be done (why, in words)."""


# An app's canvas (2026-11-21: the Canvas, `<app>.canvas.json`; an old .stapp.json is still the project's).
CANVAS_SUFFIX: str = ".canvas.json"


def kind_of(path: str) -> str:
    """notebook, script or app by the file's ending, structure for a structures/ file (Structures); ""
    for any other file."""
    parts = path.replace("\\", "/").split("/")
    if len(parts) == 2 and parts[0] == "structures" and structures.format_of(parts[1]):
        return "structure"
    if parts[-1].lower().endswith(CANVAS_SUFFIX):
        return "app"  # a canvas (the Streamlit extension's): the project's app
    try:
        return notebooks.kind_of(path)
    except notebooks.NotebookError:
        return ""


# ===== the project's app data: .sab/blades and .sab/dashboards =====


def app_entry(name: str) -> bool:
    """An entry of the project's own definitions: one JSON file directly in .sab/blades or .sab/dashboards."""
    folder, _, file = name.rpartition("/")
    return folder in (BLADES, DASHBOARDS, OLD_DASHBOARDS) and bool(_FILE_NAME.fullmatch(file))


def blade_entry(name: str) -> bool:
    return app_entry(name) and name.startswith(BLADES + "/")


# ===== documents =====


def documents(files: Iterable[tuple[str, int, float]], kind: str | None = None) -> list[dict[str, Any]]:
    """The project's notebooks, scripts and apps from its files (path inside it, size, last change), by
    kind then name; `made`: an export the app writes (data.py, pages/*.py)."""
    if kind is not None and kind not in KINDS:
        raise ScopeError("kind is notebook, script, app or structure.")
    found = []
    for relative, size, modified in files:
        if relative.startswith(APP_FOLDER + "/"):
            continue
        found_kind = kind_of(relative)
        if not found_kind or (kind and found_kind != kind):
            continue
        found.append(
            {
                "path": relative,
                "name": posixpath.basename(relative),
                "kind": found_kind,
                "size": size,
                "modified": modified,
                "made": bool(_MADE.match(relative)),
            }
        )
    order = {k: i for i, k in enumerate(KINDS)}
    return sorted(found, key=lambda d: (order[d["kind"]], d["made"], d["path"].casefold()))


DATA_NOTEBOOK: str = "data.ipynb"  # the project's data notebook, at its top
DATA_ROLE: str = "data"
APP_ROLE: str = "app"


def notebook_roles(documents: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Each notebook's role by its path inside the project (the owner, 2026-11-16: "data notebooks and
    app notebooks"): "data" for THE data notebook, data.ipynb at the project's top; "app" for every
    other notebook, whether a canvas uses it yet or not. Other documents have none."""
    roles: dict[str, str] = {}
    for document in documents:
        if document.get("kind") != "notebook":
            continue
        path = str(document["path"])
        roles[path] = DATA_ROLE if path.replace("\\", "/").casefold() == DATA_NOTEBOOK else APP_ROLE
    return roles


def notebook_kind(path: str, project: str | None) -> str | None:
    """A notebook's kind by its whole path and the open project's folder (None: no project open):
    "data" for data.ipynb (at the project's top, or anywhere with no project: its Data mode is its
    own), "app" for any other notebook in the project, "" (plain) for one outside it. None: not a
    notebook."""
    whole = path.replace("\\", "/")
    if not whole.casefold().endswith(".ipynb"):
        return None
    name = posixpath.basename(whole)
    if project is None:
        return DATA_ROLE if name.casefold() == DATA_NOTEBOOK else ""
    top = project.replace("\\", "/").rstrip("/")
    if not whole.casefold().startswith(top.casefold() + "/"):
        return ""
    return notebook_roles([{"path": whole[len(top) + 1 :], "kind": "notebook"}])[whole[len(top) + 1 :]]


def inside(folder: str, relative: str) -> str:
    """A file's whole path from the project's folder and its path inside it (the folder's own slashes)."""
    sep = "\\" if "\\" in folder and "/" not in folder else "/"
    return folder.rstrip("\\/") + sep + relative.replace("/", sep)


def free_name(relative: str, taken: Iterable[str]) -> str:
    """`relative`, or the next name the project does not have: analysis 2.ipynb, sales 2.stapp.json."""
    used = {t.casefold() for t in taken}
    if relative.casefold() not in used:
        return relative
    folder, _, file = relative.rpartition("/")
    lowered = file.lower()
    ending = notebooks.APP_SUFFIX if lowered.endswith(notebooks.APP_SUFFIX) else posixpath.splitext(file)[1]
    stem = file[: len(file) - len(ending)] if ending else file
    n = 2
    while True:
        name = f"{stem} {n}{ending}"
        candidate = f"{folder}/{name}" if folder else name
        if candidate.casefold() not in used:
            return candidate
        n += 1


def chosen(raw: Any, field: str) -> list[str] | None:
    """A list of names or paths an import names (None: not sent)."""
    if raw is None:
        return None
    if not isinstance(raw, list) or not all(isinstance(r, str) and r.strip() for r in raw):
        raise ScopeError(f"{field} is a list of names.")
    if len(raw) > MAX_IMPORT:
        raise ScopeError(f"At most {MAX_IMPORT} {field} in one import.")
    return [r.strip() for r in raw]


def pick(available: Sequence[str], wanted: list[str] | None, what: str) -> list[str]:
    """The ones asked for, each one of `available` (names compared without case); all when None."""
    if wanted is None:
        return list(available)
    by_key = {a.casefold(): a for a in available}
    missing = [w for w in wanted if w.casefold() not in by_key]
    if missing:
        raise ScopeError(f"No {what} {', '.join(missing[:5])} there.")
    return [by_key[w.casefold()] for w in wanted]


# ===== a connection's passwords on this computer =====


def needs_passwords(
    secrets: Mapping[str, bool],
    variables: Mapping[str, Mapping[str, str]],
    present: Callable[[str], bool],
    vault_covers: Callable[[str], bool],
    typed: Iterable[str],
) -> list[str]:
    """The passwords a connection asks for that nothing on this computer gives: not saved in its keyring
    (`secrets`: name -> saved), not an environment variable, no vault mapping it, no secret blade asking
    for it; and a variable of its own Python set to come from an environment variable that is not set."""
    asked = set(typed)
    missing = [
        name
        for name, saved in secrets.items()
        if not saved and not present(name) and not vault_covers(name) and name not in asked
    ]
    for name, source in variables.items():
        if source.get("from") == "env":
            env = source.get("env") or name
            if not present(env) and env not in missing:
                missing.append(env)
    return missing


def blade_record(file: str, raw: bytes) -> dict[str, Any] | None:
    """A saved blade's file (the blade store's JSON) as an import lists it: its name, what it is, and
    whether it is a connection. None: not a blade's file."""
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("name"), str) or not data["name"].strip():
        return None
    kind = str(data.get("kind") or "other")
    template = data.get("template") if isinstance(data.get("template"), str) else None
    return {
        "name": data["name"],
        "file": file,
        "kind": kind,
        "template": template,
        "connection": connections.connection_kind(kind, template),
        "description": str(data.get("description") or "")[:300],
    }


def name_of(where: str) -> str:
    """A place's name as a project's (its folder's or its file's name)."""
    return where.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def password_fix(connection: str, missing: list[str]) -> dict[str, Any]:
    """What the page shows for a connection with no password source here, and the click that fixes it."""
    return {
        "missing": missing,
        "message": "Needs a password on this computer",
        "fix": {"kind": "password", "label": "Set the password", "connection": connection},
    }
