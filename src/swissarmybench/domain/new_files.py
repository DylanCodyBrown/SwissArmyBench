"""New file on the Scripts page (the owner, 2026-11-27: "turn the + new script on the scripts into a drop down
combo that asks what file type you wanna create. SQL python json etc. then scaffolds it for you").

The file types as data (TYPES: the dropdown's lines, each one's ending, the folder it starts in, the page it
opens on and how its tab is drawn), a name checked and its ending filled in (named), the folder inside the
project (folder_of), the one sentence a taken name is refused with (place), and each type's starter text: one
function a type (python_starter, sql_starter, json_starter, yaml_starter, toml_starter, xml_starter,
markdown_starter, text_starter, notebook_starter), reached by starter(). A notebook's is the same empty
notebook the Notebooks page saves (domain/notebooks.py). Pure rules, no I/O.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from swissarmybench.domain import notebooks, sql_files
from swissarmybench.domain.script_ide import valid_identifier

DEFAULT_TYPE = "python"  # Ctrl+N's, and a call that names no type
MAX_NAME = 120
SQL_ROWS = 100  # the first rows a new SQL file selects


class NewFileError(ValueError):
    """A new file that cannot be made as asked: one plain sentence."""


class NameTaken(NewFileError):
    """A file of that name is there already."""


@dataclass(frozen=True)
class FileType:
    id: str
    label: str  # the dropdown's line
    endings: tuple[str, ...]  # the first is filled in; the others are kept as typed
    folder: str  # where it starts, inside the project ("" its top)
    page: str  # the page it opens on (domain/workbench_pages.py)
    kind: str  # how its tab is drawn: script, sql, structure, text, notebook
    icon: str
    words: str  # what the dialog says it makes
    suggested: str  # the name the dialog starts with

    @property
    def ending(self) -> str:
        return self.endings[0]

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "ending": self.ending,
            "endings": list(self.endings),
            "folder": self.folder,
            "page": self.page,
            "kind": self.kind,
            "icon": self.icon,
            "words": self.words,
            "suggested": self.suggested,
        }


TYPES: tuple[FileType, ...] = (
    FileType(
        "python",
        "Python script",
        (".py",),
        "scripts",
        "scripts",
        "script",
        "python",
        "A module with a typed main() that runs when the file is run.",
        "untitled",
    ),
    FileType(
        "sql",
        "SQL file",
        (".sql",),
        "scripts",
        "scripts",
        "sql",
        "sql",
        "Run file builds the open table named after the file.",
        "query",
    ),
    FileType(
        "json",
        "JSON",
        (".json",),
        "structures",
        "scripts",
        "structure",
        "json",
        "An empty object.",
        "data",
    ),
    FileType(
        "yaml",
        "YAML",
        (".yaml", ".yml"),
        "structures",
        "scripts",
        "structure",
        "json",
        "An empty mapping.",
        "settings",
    ),
    FileType(
        "toml",
        "TOML",
        (".toml",),
        "structures",
        "scripts",
        "structure",
        "json",
        "An empty table.",
        "settings",
    ),
    FileType(
        "xml",
        "XML",
        (".xml",),
        "structures",
        "scripts",
        "structure",
        "json",
        "One empty root element.",
        "data",
    ),
    FileType(
        "markdown",
        "Markdown",
        (".md",),
        "",
        "scripts",
        "text",
        "markdown",
        "A heading with the file's name.",
        "notes",
    ),
    FileType("text", "Plain text", (".txt",), "", "scripts", "text", "note", "An empty file.", "notes"),
    FileType(
        "notebook",
        "Notebook",
        (".ipynb",),
        "",
        "notebooks",
        "notebook",
        "notebook",
        "An empty notebook: it opens on the Notebooks page.",
        "untitled",
    ),
)
_BY_ID: dict[str, FileType] = {t.id: t for t in TYPES}
# Endings that belong to an owner of their own (the Canvas, a workbook's design, an old app's canvas).
_NOT_OURS: tuple[str, ...] = (".canvas.json", ".design.json", ".stapp.json")
_BAD_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_STATE_FOLDER = ".sab"
_NAME_RULE = 'no folder, none of < > : " / \\ | ? *, and not starting with a dot'


def types() -> list[dict[str, Any]]:
    """The file types as data, in the dropdown's order (GET /scripts/files/new)."""
    return [t.to_json() for t in TYPES]


def type_of(value: Any) -> FileType:
    """The type a call names (none: a Python script)."""
    if value is None or value == "":
        return _BY_ID[DEFAULT_TYPE]
    found = _BY_ID.get(value.strip().lower()) if isinstance(value, str) else None
    if found is None:
        raise NewFileError(f"type is one of: {', '.join(_BY_ID)}.")
    return found


def stem_of(name: str, kind: FileType) -> str:
    """A file's name without its type's ending."""
    lowered = name.lower()
    ending = next((e for e in kind.endings if lowered.endswith(e)), "")
    return name[: len(name) - len(ending)] if ending else name


def named(kind: FileType, name: Any) -> str:
    """The file's name with its type's ending: filled in when left out, another type's refused. A Python
    script's is a module's name (letters, digits and _), so it can be imported."""
    if not isinstance(name, str) or not name.strip():
        raise NewFileError("Give the file a name.")
    name = name.strip()
    if name.startswith(".") or name.endswith((".", " ")) or _BAD_CHARACTERS.search(name):
        raise NewFileError(f"{name!r} is not a file name: {_NAME_RULE}.")
    lowered = name.lower()
    if not lowered.endswith(kind.endings):
        other = next((t for t in TYPES if t is not kind and lowered.endswith(t.endings)), None)
        if other is not None:
            raise NewFileError(
                f"{name} names a {other.label} file: pick {other.label}, or end the name with {kind.ending}."
            )
        name += kind.ending
    if lowered.endswith(_NOT_OURS) or name.lower().endswith(_NOT_OURS):
        raise NewFileError(f"{name} is a name the app keeps for its own files: pick another.")
    stem = stem_of(name, kind)
    if not stem.strip():
        raise NewFileError("Give the file a name.")
    if len(name) > MAX_NAME:
        raise NewFileError(f"A file's name is at most {MAX_NAME} characters.")
    if kind.id == "python" and not valid_identifier(stem):
        raise NewFileError(
            f"{stem!r} is not a module's name: letters, digits and _, not starting with a digit."
        )
    return str(name)


def folder_of(kind: FileType, folder: Any) -> str:
    """The folder inside the project ("" its top; none given: the type's own), with / between its parts. One
    that climbs out, starts at a drive or a root, or is hidden (the app's .sab/ among them) is refused."""
    if folder is None:
        return kind.folder
    if not isinstance(folder, str):
        raise NewFileError("folder is a folder inside the project.")
    given = folder.strip().replace("\\", "/")
    if given.startswith("/") or re.match(r"^[A-Za-z]:", given):
        raise NewFileError(
            f"{folder} is not inside the project: name a folder of the project, such as scripts."
        )
    parts = [p.strip() for p in given.split("/") if p.strip() and p.strip() != "."]
    for part in parts:
        if part == "..":
            raise NewFileError(f"{folder} is not inside the project: name a folder of the project.")
        if part.startswith(".") or part == _STATE_FOLDER:
            raise NewFileError(f"{part} is a hidden folder: a new file goes in one the project shows.")
        if _BAD_CHARACTERS.search(part):
            raise NewFileError(f"{part!r} is not a folder's name.")
    return "/".join(parts)


def place(kind: FileType, name: Any, folder: Any, taken: Callable[[str], bool]) -> str:
    """Where the new file goes, inside the project (scripts/orders.sql); a name already taken is refused in
    one sentence. `taken`: is this path inside the project there already?"""
    file_name = named(kind, name)
    inside = folder_of(kind, folder)
    relative = f"{inside}/{file_name}" if inside else file_name
    if taken(relative):
        raise NameTaken(f"{relative} is there already: pick another name.")
    return relative


def folders(listed: Any) -> list[str]:
    """The folders the dialog offers: the project's top (""), each type's own, and every folder that holds a
    file the page lists; sorted, each once."""
    found = {t.folder for t in TYPES}
    for path in listed:
        parts = str(path).replace("\\", "/").split("/")[:-1]
        if any(p.startswith(".") for p in parts):
            continue
        found.update("/".join(parts[:i]) for i in range(1, len(parts) + 1))
    return sorted(found, key=lambda f: (f != "", f.casefold()))


# ===== the starters, one function a type =====


def python_starter(name: str) -> str:
    """A module: its docstring, the future import, and a typed main() under the main guard."""
    stem = name[: -len(".py")] if name.lower().endswith(".py") else name
    return (
        f'"""{stem}: what this script does."""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        "\n"
        "def main() -> None:\n"
        '    """Run the script."""\n'
        "\n"
        "\n"
        'if __name__ == "__main__":\n'
        "    main()\n"
    )


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def sql_starter(connection: str | None = None, table: str | None = None) -> str:
    """A SQL file: its `-- connection:` line (DuckDB over the open tables says so in a comment: a header
    naming none means the same, domain/sql_files.py), then the first rows of an open table, else a hint."""
    chosen = connection.strip() if isinstance(connection, str) and connection.strip() else None
    if chosen is not None:
        word = re.sub(r"[^A-Za-z0-9_]+", "_", chosen).strip("_") or "it"
        lines = [
            f"-- Runs on {chosen}, in its own SQL. Run file (F5) builds the table named after this file.",
            f"-- SELECT * FROM a_table_of_{word};",  # noqa: S608 (a comment line of a starter file)
        ]
        return sql_files.with_connection("\n".join(lines) + "\n", chosen)
    lines = [
        f"-- {sql_files.HEADER_WORD}:",
        "-- Runs in DuckDB over the open tables ([Connection].table reads a connection's).",
    ]
    if table:
        lines += ["SELECT *", f"FROM {_quoted(table)}", f"LIMIT {SQL_ROWS};"]
    else:
        lines += [
            "-- No table is open yet: open one on the Tables page, then name it here.",
            f"-- SELECT * FROM a_table LIMIT {SQL_ROWS};",  # noqa: S608 (a comment line of a starter file)
        ]
    return "\n".join(lines) + "\n"


def json_starter() -> str:
    return "{}\n"


def yaml_starter() -> str:
    return "{}\n"


def toml_starter(name: str) -> str:
    """An empty TOML document: a comment naming the file (no key is a valid, empty table)."""
    return f"# {name}\n"


def xml_starter() -> str:
    return '<?xml version="1.0" encoding="UTF-8"?>\n<root/>\n'


def markdown_starter(name: str) -> str:
    stem = name[: -len(".md")] if name.lower().endswith(".md") else name
    return f"# {stem}\n"


def text_starter() -> str:
    return ""


def notebook_starter() -> str:
    """An empty notebook, as the Notebooks page saves one with no cells."""
    return notebooks.write_notebook([])


def starter(kind: FileType, name: str, options: Mapping[str, Any] | None = None) -> str:
    """The type's starter text for a file named `name`. options: a SQL file's `connection` (none: DuckDB over
    the open tables) and `table` (an open table to select from)."""
    given = options or {}
    by_type: dict[str, Callable[[], str]] = {
        "python": lambda: python_starter(name),
        "sql": lambda: sql_starter(given.get("connection"), given.get("table")),
        "json": json_starter,
        "yaml": yaml_starter,
        "toml": lambda: toml_starter(name),
        "xml": xml_starter,
        "markdown": lambda: markdown_starter(name),
        "text": text_starter,
        "notebook": notebook_starter,
    }
    return by_type[kind.id]()
