"""New file (the owner, 2026-11-27: "turn the + new script on the scripts into a drop down combo that asks
what file type you wanna create. SQL python json etc. then scaffolds it for you"; then "Everything should get
a name or the file is not created and yes every file should go scaffolding file on the back. The list of
follow-ups available should change with projects").

Every new file is named first and written by the server with its type's starter: there is no untitled file.
The file types as data (TYPES: the dropdown's lines, each one's ending, the folder it starts in, the page it
opens on, how its tab is drawn, what its dialog asks: name, folder, a SQL file's connection, a diagram's
kind), the ones a project type adds (from_extension: its mode's `new_files`, made by its extension's own
"new" path), which are offered (offered: with no project only the loose ones), a name checked and its ending
filled in (named), the folder inside the project (folder_of) or any folder of the disk with no project open
(loose_place), the one sentence a taken name is refused with (place), and each type's starter text, one
function a type, reached by starter(): code (Python, SQL), structures (JSON, YAML, TOML, XML), a notebook
(the same empty notebook the Notebooks page saves), and the project's documentation ("The idea is the
context documentation for a project can be created and edited"): Markdown, a README, a decision record, a
data dictionary (the open tables' columns by name and type, never a value), an HTML page and a Mermaid
diagram (the UML kinds Mermaid draws). Pure rules, no I/O.
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
    asks: tuple[str, ...] = ("name", "folder")  # what its dialog asks (a SQL file: connection; variant)
    variants: tuple[tuple[str, str], ...] = ()  # (id, label): a diagram's kinds
    loose: bool = True  # it can be made with no project open, in any folder
    maker: str = ""  # an extension's own type: its maker's id (services/hooks.py new_file_makers)

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
            "asks": list(self.asks),
            "variants": [{"id": v, "label": label} for v, label in self.variants],
            "loose": self.loose,
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
        "script",
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
        asks=("name", "folder", "connection"),
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
        "html",
        "HTML page",
        (".html", ".htm"),
        "docs",
        "scripts",
        "text",
        "code",
        "A small HTML page: its Preview draws it in a walled-off frame.",
        "page",
    ),
    FileType(
        "diagram",
        "Diagram",
        (".mmd", ".mermaid"),
        "docs/diagrams",
        "scripts",
        "text",
        "chart",
        "A Mermaid diagram: pick its kind; its Preview draws it.",
        "diagram",
        asks=("name", "folder", "variant"),
        variants=(
            ("flowchart", "Flowchart (activity)"),
            ("class", "Class diagram"),
            ("sequence", "Sequence diagram"),
            ("state", "State diagram"),
            ("er", "Entity-relationship diagram"),
            ("gantt", "Gantt chart"),
        ),
    ),
    FileType(
        "readme",
        "README",
        (".md",),
        "",
        "scripts",
        "text",
        "markdown",
        "What the project is for, its data and how to run it.",
        "README",
    ),
    FileType(
        "decision",
        "Decision record",
        (".md",),
        "docs/decisions",
        "scripts",
        "text",
        "markdown",
        "A decision: its date, context, the decision and its consequences.",
        "0001-decision",
    ),
    FileType(
        "dictionary",
        "Data dictionary",
        (".md",),
        "docs",
        "scripts",
        "text",
        "markdown",
        "The open tables and their columns, by name and type (never a value).",
        "data-dictionary",
    ),
    FileType(
        "notebook",
        "Notebook",
        (".ipynb",),
        "",
        "notebooks",
        "notebook",
        "notebook",
        "An empty notebook: it opens on the Notebooks page.",
        "notebook",
    ),
)
_BY_ID: dict[str, FileType] = {t.id: t for t in TYPES}
# Endings that belong to an owner of their own (the Canvas, a workbook's design, an old app's canvas).
_NOT_OURS: tuple[str, ...] = (".canvas.json", ".design.json", ".stapp.json")
_BAD_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_STATE_FOLDER = ".sab"
_NAME_RULE = 'no folder, none of < > : " / \\ | ? *, and not starting with a dot'


_TEXT = ("id", "label", "page", "kind", "icon", "words", "suggested")


def from_extension(raw: Any) -> FileType | None:
    """A file type a project type adds (its mode's `new_files` item), read loosely: {id, label, ending,
    folder?, page, kind?, icon?, words?, suggested?, asks?, loose?}. Its extension makes it by its own "new"
    path (the maker registered under its id); one with no id, label or ending, or a base type's id, none."""
    if not isinstance(raw, Mapping):
        return None
    given = {k: str(raw.get(k) or "").strip() for k in _TEXT}
    ending = str(raw.get("ending") or "").strip().lower()
    if not given["id"] or not given["label"] or not ending.startswith(".") or given["id"] in _BY_ID:
        return None
    asks = raw.get("asks")
    return FileType(
        given["id"],
        given["label"],
        (ending,),
        str(raw.get("folder") or "").strip(),
        given["page"] or "scripts",
        given["kind"] or given["id"],
        given["icon"] or "code",
        given["words"],
        given["suggested"] or "new",
        asks=tuple(str(a) for a in asks) if isinstance(asks, list | tuple) else ("name",),
        loose=raw.get("loose") is True,
        maker=given["id"],
    )


def offered(extra: Any = (), project: bool = True) -> list[FileType]:
    """The types the New file list offers: the base's, then the open project's type's own (its mode's
    `new_files`); with no project open only the ones that can be made loose."""
    more = [t for t in (from_extension(raw) for raw in extra or ()) if t is not None]
    seen: set[str] = set()
    out: list[FileType] = []
    for kind in (*TYPES, *more):
        if kind.id not in seen and (project or kind.loose):
            seen.add(kind.id)
            out.append(kind)
    return out


def types(extra: Any = (), project: bool = True) -> list[dict[str, Any]]:
    """The file types as data, in the dropdown's order (GET /scripts/files/new)."""
    return [t.to_json() for t in offered(extra, project)]


def type_of(value: Any, extra: Any = (), project: bool = True) -> FileType:
    """The type a call names (none: a Python script), among the ones offered."""
    known = {t.id: t for t in offered(extra, project)}
    if value is None or value == "":
        return known[DEFAULT_TYPE]
    asked = value.strip().lower() if isinstance(value, str) else ""
    found = known.get(asked)
    if found is None:
        everywhere = {t.id for t in offered(extra, True)}
        if asked in everywhere:
            raise NewFileError(f"Open a project first: a {asked} is made in its folder.")
        raise NewFileError(f"type is one of: {', '.join(known)}.")
    return found


NO_NAME = "Give the file a name: a new file is made only once it is named."


def variant_of(kind: FileType, value: Any) -> str:
    """A diagram's kind as a call names it (none: the type's first); "" for a type with none."""
    if not kind.variants:
        return ""
    if value is None or value == "":
        return kind.variants[0][0]
    asked = value.strip().lower() if isinstance(value, str) else ""
    if asked not in {v for v, _ in kind.variants}:
        raise NewFileError(f"variant is one of: {', '.join(v for v, _ in kind.variants)}.")
    return asked


def stem_of(name: str, kind: FileType) -> str:
    """A file's name without its type's ending."""
    lowered = name.lower()
    ending = next((e for e in kind.endings if lowered.endswith(e)), "")
    return name[: len(name) - len(ending)] if ending else name


def named(kind: FileType, name: Any) -> str:
    """The file's name with its type's ending: filled in when left out, another type's refused. A Python
    script's is a module's name (letters, digits and _), so it can be imported."""
    if not isinstance(name, str) or not name.strip():
        raise NewFileError(NO_NAME)
    name = name.strip()
    if name.startswith(".") or name.endswith((".", " ")) or _BAD_CHARACTERS.search(name):
        raise NewFileError(f"{name!r} is not a file name: {_NAME_RULE}.")
    lowered = name.lower()
    if not lowered.endswith(kind.endings):
        other = next(
            (t for t in TYPES if t is not kind and t.endings != kind.endings and lowered.endswith(t.endings)),
            None,
        )
        if other is not None:
            raise NewFileError(
                f"{name} names a {other.label} file: pick {other.label}, or end the name with {kind.ending}."
            )
        name += kind.ending
    if not kind.maker and (lowered.endswith(_NOT_OURS) or name.lower().endswith(_NOT_OURS)):
        raise NewFileError(f"{name} is a name the app keeps for its own files: pick another.")
    stem = stem_of(name, kind)
    if not stem.strip():
        raise NewFileError(NO_NAME)
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


def loose_place(kind: FileType, name: Any, folder: Any, taken: Callable[[str], bool]) -> str:
    """With no project open: the new file's whole path, in the folder the user picked (any folder of the
    disk, named whole). `taken`: is this whole path there already?"""
    file_name = named(kind, name)
    if not isinstance(folder, str) or not folder.strip():
        raise NewFileError("No project is open: say which folder the file goes in (its whole path).")
    given = folder.strip().replace("\\", "/")
    if not (given.startswith("/") or re.match(r"^[A-Za-z]:/", given)):
        raise NewFileError(
            f"{folder} is not a whole path: with no project open a new file's folder is named whole."
        )
    full = given.rstrip("/") + "/" + file_name
    if taken(full):
        raise NameTaken(f"{file_name} is there already: pick another name.")
    return full


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


def _words(name: str, ending: str = ".md") -> str:
    """A file's name as a heading's words: its ending and a leading number gone, - and _ as spaces."""
    stem = name[: -len(ending)] if name.lower().endswith(ending) else name
    said = re.sub(r"^\d+[-_ ]+", "", stem).replace("-", " ").replace("_", " ").strip()
    return (said[:1].upper() + said[1:]) if said else stem


def html_starter(name: str) -> str:
    """A small, valid HTML5 page: nothing loaded from outside (its Preview's frame loads nothing)."""
    stem = re.sub(r"\.html?$", "", name, flags=re.IGNORECASE)
    title = stem.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "  <head>\n"
        '    <meta charset="utf-8" />\n'
        '    <meta name="viewport" content="width=device-width, initial-scale=1" />\n'
        f"    <title>{title}</title>\n"
        "    <style>\n"
        "      body { font-family: system-ui, sans-serif; margin: 2rem; line-height: 1.5; }\n"
        "    </style>\n"
        "  </head>\n"
        "  <body>\n"
        f"    <h1>{title}</h1>\n"
        "    <p>What this page shows.</p>\n"
        "  </body>\n"
        "</html>\n"
    )


# A Mermaid diagram's starters, one a kind: each a small, valid, made-up example.
DIAGRAMS: dict[str, str] = {
    "flowchart": (
        "flowchart TD\n"
        "    start([Order received]) --> check{In stock?}\n"
        "    check -- Yes --> pack[Pack the order]\n"
        "    check -- No --> wait[Wait for the supplier]\n"
        "    wait --> pack\n"
        "    pack --> ship([Ship it])\n"
    ),
    "class": (
        "classDiagram\n"
        "    class Customer {\n"
        "        +int id\n"
        "        +string name\n"
        "        +place_order() Order\n"
        "    }\n"
        "    class Order {\n"
        "        +int id\n"
        "        +date placed\n"
        "        +total() float\n"
        "    }\n"
        "    class OrderLine {\n"
        "        +int quantity\n"
        "        +float price\n"
        "    }\n"
        '    Customer "1" --> "*" Order : places\n'
        '    Order "1" *-- "*" OrderLine : has\n'
    ),
    "sequence": (
        "sequenceDiagram\n"
        "    actor User\n"
        "    participant App\n"
        "    participant Database\n"
        "    User->>App: Open the orders table\n"
        "    App->>Database: SELECT the first rows\n"
        "    Database-->>App: Rows\n"
        "    App-->>User: The table\n"
    ),
    "state": (
        "stateDiagram-v2\n"
        "    [*] --> Draft\n"
        "    Draft --> Submitted : submit\n"
        "    Submitted --> Approved : approve\n"
        "    Submitted --> Draft : send back\n"
        "    Approved --> [*]\n"
    ),
    "er": (
        "erDiagram\n"
        "    CUSTOMER ||--o{ ORDER : places\n"
        "    ORDER ||--|{ ORDER_LINE : has\n"
        "    CUSTOMER {\n"
        "        int id PK\n"
        "        string name\n"
        "    }\n"
        "    ORDER {\n"
        "        int id PK\n"
        "        int customer_id FK\n"
        "        date placed\n"
        "    }\n"
        "    ORDER_LINE {\n"
        "        int order_id FK\n"
        "        int quantity\n"
        "    }\n"
    ),
    "gantt": (
        "gantt\n"
        "    title A made-up plan\n"
        "    dateFormat YYYY-MM-DD\n"
        "    section Build\n"
        "    Load the data      :load, 2026-01-05, 5d\n"
        "    Model the tables   :model, after load, 4d\n"
        "    section Deliver\n"
        "    Write the report   :report, after model, 3d\n"
    ),
}


def diagram_starter(variant: str) -> str:
    return DIAGRAMS.get(variant) or DIAGRAMS["flowchart"]


def readme_starter(project: str) -> str:
    """A project's README: what it is for, its data, how to run it, where its decisions are."""
    return (
        f"# {project or 'Project'}\n"
        "\n"
        "What this project is for, in a sentence or two.\n"
        "\n"
        "## Data\n"
        "\n"
        "Where the data comes from and what each table holds.\n"
        "\n"
        "## How to run it\n"
        "\n"
        "1. Open the project in Swiss Army Bench.\n"
        "2. Run `data.ipynb`.\n"
        "\n"
        "## Decisions\n"
        "\n"
        "- [ ] Write down the first decision (New file, Decision record).\n"
    )


def decision_starter(name: str, date: str) -> str:
    """A decision record: its title, date, context, the decision and its consequences."""
    return (
        f"# {_words(name)}\n"
        "\n"
        f"- Date: {date}\n"
        "- Status: proposed\n"
        "\n"
        "## Context\n"
        "\n"
        "What made a decision necessary.\n"
        "\n"
        "## Decision\n"
        "\n"
        "What was decided.\n"
        "\n"
        "## Consequences\n"
        "\n"
        "What follows from it: what gets easier, what gets harder.\n"
    )


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def dictionary_starter(tables: Any) -> str:
    """A data dictionary: each open table and its columns, by name and type only (never a value, a count or
    a row), with a Description column to fill in. `tables`: [{name, columns: [{name, type}]}]."""
    lines = ["# Data dictionary", ""]
    listed = [t for t in tables or () if isinstance(t, Mapping) and t.get("name")]
    if not listed:
        lines += ["No table is open yet: open the project's tables, then make this file again.", ""]
    for table in sorted(listed, key=lambda t: str(t["name"]).casefold()):
        lines += [f"## {table['name']}", "", "| Column | Type | Description |", "|---|---|---|"]
        for column in table.get("columns") or ():
            lines.append(f"| {_cell(column.get('name', ''))} | {_cell(column.get('type', ''))} |  |")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def notebook_starter() -> str:
    """An empty notebook, as the Notebooks page saves one with no cells."""
    return notebooks.write_notebook([])


def starter(kind: FileType, name: str, options: Mapping[str, Any] | None = None) -> str:
    """The type's starter text for a file named `name`. options: a SQL file's `connection` (none: DuckDB over
    the open tables) and `table` (an open table to select from); a diagram's `variant`; a README's `project`
    (its name); a decision record's `date`; a data dictionary's `tables`."""
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
        "html": lambda: html_starter(name),
        "diagram": lambda: diagram_starter(str(given.get("variant") or "")),
        "readme": lambda: readme_starter(str(given.get("project") or "")),
        "decision": lambda: decision_starter(name, str(given.get("date") or "")),
        "dictionary": lambda: dictionary_starter(given.get("tables")),
    }
    return by_type[kind.id]()
