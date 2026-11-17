"""The library (Plans/library.plan.md; the owner, 2026-11-17: "Apis, Connections they live OUTSIDE of the
project, I dont wanna have to go hunt an api every project" / "that library is the thing I wanted to push
to a github repo so it can be shared as a code base with fellow users later"). This computer's connections,
APIs, vaults, blades, relationship sets, variables and connection colours, in one folder of text files made
to be a Git repository, shared by every project.

  layout      connections/<name>.blade.py, vaults/<name>.blade.py, blades/<name>.blade.py, apis/<name>/,
              relationship-sets/<name>.relationships.json, variables.toml, colours.toml, local/ (this computer
              only, git-ignored), README.md and .gitignore (made on first use, the user's to edit)
  which       a blade's folder by what it is: a key vault in vaults/, a connection in connections/, the
              rest in blades/ (an API's blades stay in its own apis/<name>/ folder)
  stable      one file per item, sorted keys, the same text for the same thing: a save that changes
              nothing changes no byte, so a Git diff shows only what the user changed
  never       a secret's value, a token, a row of data: secrets stay in this computer's keyring, a
              connection's password names where it comes from
  variables   variables.toml holds each variable's name and source (and a shareable plain value);
              local/variables.toml the plain values marked this computer only
  migration   an older project's own .sab/blades copied in: the same text skipped, a different one
              kept as "<name> from <project>" (a blade's name has no brackets) and said

Pure rules: no I/O, no clock.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Iterable
from typing import Any

from swissarmybench.domain.blades import Blade
from swissarmybench.domain.connections import connection_kind

FORMAT: int = 1
CONNECTIONS: str = "connections"
VAULTS: str = "vaults"
BLADES: str = "blades"
APIS: str = "apis"
RELATIONSHIP_SETS: str = "relationship-sets"
OLD_TANGS: str = "tangs"  # the old name (2026-11-17), one release: moved to relationship-sets/ at start
LOCAL: str = "local"
VARIABLES_FILE: str = "variables.toml"
LOCAL_VARIABLES_FILE: str = f"{LOCAL}/variables.toml"
COLOURS_FILE: str = "colours.toml"
BLADE_FOLDERS: tuple[str, ...] = (CONNECTIONS, VAULTS, BLADES)
NEVER: tuple[str, ...] = ("passwords and secrets", "tokens", "rows of data")

README: str = """# Swiss Army Bench library

This computer's connections, APIs, key vaults, blades, relationship sets, variables and connection
colours, shared by every project. Each item is one text file, so the folder works as a Git repository:
commit and push it with your own tools, and a teammate who clones it and points Swiss Army Bench at it
(Settings, Library) gets the same items.

    connections/   each connection (a .blade.py file: its settings and code)
    vaults/        each key vault
    apis/          each API: its client, its blades, its OpenAPI document
    blades/        functions, analyses, snippets
    relationship-sets/  saved sets of relationships
    variables.toml each variable's name and where its value comes from
    colours.toml   each connection's colour
    local/         this computer only (not committed: see .gitignore)

Nothing here holds a password, a secret, a token or a row of data. Secrets stay in each computer's keyring;
on another computer each connection asks for its missing passwords the first time it runs.
"""

GITIGNORE: str = """# This computer only: paths and values that differ per computer.
local/
# Files being written.
*.tmp
*.part
"""


class LibraryError(ValueError):
    """A library folder that cannot be used as asked (why, in words)."""


def folder_for(kind: str, template: str | None) -> str:
    """The library folder a saved blade's file goes in: vaults/, connections/ or blades/."""
    found = connection_kind(kind, template)
    if found == "vault":
        return VAULTS
    return CONNECTIONS if found else BLADES


def toml_string(value: str) -> str:
    """A TOML basic string that reads back exactly (JSON's escapes are TOML's; DEL escaped too)."""
    return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")


def _bare(name: str) -> str:
    return name if re.fullmatch(r"[A-Za-z0-9_-]+", name) else toml_string(name)


def variables_toml(shared: Any) -> str:
    """variables.toml from the Variables page's shareable record ({"format", "variables": [{"name", "from",
    "value"|"local"}]}), sorted by name: names and sources, a shareable plain value; never a secret."""
    rows = shared.get("variables", []) if isinstance(shared, dict) else []
    lines = [
        "# Each variable's name and where its value comes from (Swiss Army Bench). Never a secret's value.",
        f"format = {FORMAT}",
    ]
    for row in sorted((r for r in rows if isinstance(r, dict)), key=lambda r: str(r.get("name", ""))):
        lines += ["", f"[variables.{_bare(str(row['name']))}]"]
        for key in sorted(k for k in row if k != "name"):
            lines.append(f"{_bare(key)} = {toml_string(str(row[key]))}")
    return "\n".join(lines) + "\n"


def local_toml(local: Any) -> str:
    """local/variables.toml: the plain values marked this computer only, sorted by name."""
    values = local.get("values", {}) if isinstance(local, dict) else {}
    lines = [
        "# This computer only (git-ignored): plain values marked local.",
        f"format = {FORMAT}",
        "",
        "[values]",
    ]
    for name in sorted(values):
        lines.append(f"{_bare(str(name))} = {toml_string(str(values[name]))}")
    return "\n".join(lines) + "\n"


def read_variables_toml(text: str) -> dict[str, Any] | None:
    """The shareable record from variables.toml (None: no file, or not one that can be read)."""
    data = _toml(text)
    if data is None:
        return None
    table = data.get("variables")
    rows = [
        {"name": name, **{k: str(v) for k, v in row.items()}}
        for name, row in (table.items() if isinstance(table, dict) else [])
        if isinstance(row, dict)
    ]
    return {"format": data.get("format", FORMAT), "variables": rows}


def read_local_toml(text: str) -> dict[str, Any] | None:
    data = _toml(text)
    if data is None:
        return None
    values = data.get("values")
    kept = {str(k): str(v) for k, v in values.items()} if isinstance(values, dict) else {}
    return {"format": data.get("format", FORMAT), "values": kept}


def _toml(text: str) -> dict[str, Any] | None:
    if not text.strip():
        return None
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None


_NAME_PART = re.compile(r"[^A-Za-z0-9 _.-]+")


def migrated_name(name: str, project: str, taken: Iterable[str]) -> str:
    """A project's blade that differs from the library's of the same name: "<name> from <project>" (then
    numbered), within a blade name's 64 characters and characters."""
    used = {t.casefold() for t in taken}
    where = " ".join(_NAME_PART.sub(" ", project).split()) or "project"
    stem = f"{name} from {where}"[:60].rstrip(" .-")
    candidate, number = stem, 2
    while candidate.casefold() in used:
        candidate = f"{stem[: 60 - len(str(number)) - 1].rstrip()} {number}"
        number += 1
    return candidate


def migration_words(added: list[str], renamed: dict[str, str], skipped: list[str], project: str) -> str:
    """What a project's own blades did when they came into the library, in one sentence (or "")."""
    parts = []
    if added:
        parts.append(f"{len(added)} added ({', '.join(added)})")
    if renamed:
        parts.append(
            f"{len(renamed)} kept under a new name, as the library has a different one "
            f"({', '.join(f'{old} as {new}' for old, new in renamed.items())})"
        )
    if skipped:
        parts.append(f"{len(skipped)} already there")
    if not parts:
        return ""
    return f"{project}'s connections and blades moved into your library: " + "; ".join(parts) + "."


def computer_migration_words(moved: dict[str, int], backup: str) -> str:
    """The one-time move of this computer's stores into the library, in one sentence (or "")."""
    one_file = {"variables files": "your variables", "colours files": "your connection colours"}
    said = [one_file.get(what, f"{count} {what}") for what, count in moved.items() if count]
    if not said:
        return ""
    return (
        "Your connections and blades now live in your library folder: "
        + ", ".join(said)
        + f" moved there. The old files are kept in {backup}."
    )


def saved_json(data: Any) -> Blade | None:
    """A blade from the JSON the app saved before the library (~/.swissarmybench/blades, an older
    project's .sab/blades): its record, or None when it is not one."""
    if not isinstance(data, dict) or not isinstance(data.get("name"), str):
        return None
    catalog = data.get("catalog") or {}
    return Blade(
        name=data["name"],
        kind=data.get("kind", "other"),
        code=data.get("code", ""),
        variable=data.get("variable"),
        dialect=data.get("dialect", "other"),
        catalog_language=catalog.get("language"),
        catalog_command=catalog.get("command"),
        vault_mapping={r["env"]: r["secret"] for r in data.get("vault_mapping", []) if isinstance(r, dict)},
        vault_all=data.get("vault_all") is True,
        row_limit=data["row_limit"] if isinstance(data.get("row_limit"), int) else None,
        read_command=(data.get("read") or {}).get("command"),
        variables={
            str(r["name"]): {k: str(v) for k, v in r.items() if k != "name"}
            for r in data.get("variables", [])
            if isinstance(r, dict) and "name" in r
        },
        env_names=list(data.get("env_names", [])),
        template=data.get("template"),
        description=str(data.get("description") or ""),
        tags=[str(t) for t in data.get("tags", []) if isinstance(t, str)],
        language=str(data.get("language") or ""),
        cell_name=str(data.get("cell_name") or ""),
        family=str(data.get("family") or ""),
        web_call=dict(data.get("web_call") or {}) if isinstance(data.get("web_call"), dict) else {},
        created_at=float(data.get("created_at", 0)),
        updated_at=float(data.get("updated_at", 0)),
    )


def sets_migration_words(moved: int, backup: str) -> str:
    """The one-time move of the library's old tangs/ folder to relationship-sets/, in one sentence (or "")."""
    if not backup:
        return ""
    sets = f"{moved} saved set{'' if moved == 1 else 's'} of relationships"
    return (
        f"Your {sets} now live in your library's {RELATIONSHIP_SETS} folder. "
        f"The old files are kept in {backup}."
    )
