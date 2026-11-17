"""The .sab project file: one file that holds a whole project (the owner, 2026-11-16: "a proprietary
format for projects where they can be saved in a .sab file and this file can be opened from any session
to get back to project you are working on"). Pure rules, no I/O.

A .sab is a zip, like .docx or .pbix:

    project.json            the format, the app version that wrote it, the project's name, and
                            the tables: each with its name, its source and its grids' steps;
                            the open tabs; the Workbench's documents, modes and layout; the diagram
    data.ipynb, *.ipynb,    the project's own files at their paths (code and text only: never a data
    *.py, pages/*.py, ...   file, which would carry rows)
    visualizations/visualizations.json
                            Visualizations: its cards (what a chart showed is not kept: it redraws);
                            sandbox/sandbox.json in a file saved before the Sandbox was renamed
    model.tang              the relationships
    data/<table>.parquet    only the tables ticked "Keep its rows in the file"

The owner's two choices (2026-11-16): "one file holds it all", and "rows only on a tick": a table keeps
where it came from and its steps, and is read again on open; a pasted or pushed table has no source,
so its rows go in only when ticked. A connection is named, never embedded: no secret, token or
password is ever written. Fields this version does not know are kept when the file is saved again; a
file of a newer format opens read-only.

  sources    where each table came from (Origin) as the file says it: a connection with its table or
             query, a file (relative to the .sab when it sits nearby), the notebook that makes it, a
             "+" tab's query, or pasted/pushed with rows true or false
  manifest   project.json read (leniently: unknown fields kept) and written
  entries    a zip entry's name checked: no `..`, no absolute path, no drive, no link; sizes capped
  packed     which of a working folder's files go into the file
  fixes      a table that could not come back: its state and the one click that fixes it
"""

from __future__ import annotations

import json
import ntpath
import posixpath
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from swissarmybench.domain import approvals, notebooks
from swissarmybench.domain import projects as project_rules
from swissarmybench.domain.projects import DataCell
from swissarmybench.domain.table_cells import Origin

FORMAT: int = 1
MARK_KEY: str = "swissarmybench"
MARK: str = "project"
SUFFIX: str = ".sab"
MANIFEST: str = "project.json"
MODEL: str = "model.tang"
VISUALIZATIONS: str = "visualizations/visualizations.json"
# The Sandbox's entry and manifest key before it became Visualizations (the owner, 2026-11-16): read for
# one release, never written.
OLD_SANDBOX: str = "sandbox/sandbox.json"
ROWS_FOLDER: str = "data"
MAX_NAME: int = 100
MAX_ENTRY_NAME: int = 400
MAX_TABLES: int = 200

# The project's own files that go into the file: code, text, settings and the app's pictures. A data
# file (CSV, Excel, Parquet, JSON) would carry rows: its table keeps its path instead.
PACKED_SUFFIXES: frozenset[str] = frozenset(
    {
        ".ipynb", ".py", ".md", ".txt", ".toml", ".cfg", ".ini", ".yaml", ".yml", ".css", ".js",
        ".html", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".tang",
    }
)  # fmt: skip
# Folders that are never the project's own: environments, caches, version control.
SKIPPED_FOLDERS: frozenset[str] = frozenset(
    {"__pycache__", ".venv", "venv", "env", "node_modules", ".ipynb_checkpoints", ".git", ".mypy_cache"}
)
SOURCE_KINDS: tuple[str, ...] = ("connection", "file", "cell", "query", "pasted")
_DRIVE = re.compile(r"^[A-Za-z]:")
_CONTROL = re.compile(r"[\x00-\x1f]")


class SabError(ValueError):
    """A file that is not a project this version can open, or a request it cannot do (why, in words)."""


# ===== sources: where each table came from =====


@dataclass(frozen=True)
class Source:
    """Where a table comes from, as the file says it. Never a password: a connection by its name."""

    kind: str  # connection, file, cell, query, pasted
    connection: str | None = None
    database: str = ""
    schema: str = ""
    table: str = ""
    sql: str | None = None  # a connection's query (DAX on a Power BI dataset), or a "+" tab's
    dax: bool = False
    whole: bool = True  # a connection's table: every row (else its first rows, as it was opened)
    path: str | None = None  # a file: relative to the .sab when it sits nearby, else absolute
    absolute: str | None = None  # a file: where it was when saved (tried when the relative one is gone)
    sheet: str | None = None
    notebook: str | None = None  # the project notebook that makes it, relative to the project
    rows: bool = False  # pasted or pushed: its rows are in the file (data/<table>.parquet)
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = dict(self.extra) | {"kind": self.kind}
        if self.kind == "connection":
            out |= {"connection": self.connection, "database": self.database, "schema": self.schema}
            out |= {"table": self.table, "whole": self.whole}
            if self.sql:
                out |= {"sql": self.sql, "dax": self.dax}
        elif self.kind == "file":
            out |= {"path": self.path, "absolute": self.absolute, "sheet": self.sheet}
        elif self.kind == "cell":
            out |= {"notebook": self.notebook}
        elif self.kind == "query":
            out |= {"sql": self.sql}
        else:
            out |= {"rows": self.rows}
        return out

    @property
    def needs_rows(self) -> bool:
        """No way to read it again: its rows come back only when they are in the file."""
        return self.kind == "pasted"

    def label(self) -> str:
        """Where it comes from, in a word or two: Warehouse · orders, orders.csv, data.ipynb, Pasted."""
        if self.kind == "connection":
            return " · ".join(filter(None, [self.connection, self.table or ("Query" if self.sql else "")]))
        if self.kind == "file":
            return _base(self.path or self.absolute or "")
        if self.kind == "cell":
            return _base(self.notebook or "")
        return {"query": "Query"}.get(self.kind, "Pasted")


def _text(raw: Mapping[str, Any], key: str, limit: int = 4000) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > limit:
        raise SabError(f"A table's source has a {key} that is not text.")
    return value


def read_source(raw: Any) -> Source:
    """A source as project.json has it (fields this version does not know are kept)."""
    if not isinstance(raw, dict) or raw.get("kind") not in SOURCE_KINDS:
        return Source("pasted", extra=raw if isinstance(raw, dict) else {})
    kind = str(raw["kind"])
    known = {"kind", "connection", "database", "schema", "table", "sql", "dax", "whole", "path"}
    known |= {"absolute", "sheet", "notebook", "rows"}
    extra = {k: v for k, v in raw.items() if k not in known}
    if kind == "connection":
        name = _text(raw, "connection", 200)
        if not name:
            raise SabError("A table's source names no connection.")
        return Source(
            kind,
            connection=name,
            database=_text(raw, "database", 400) or "",
            schema=_text(raw, "schema", 400) or "",
            table=_text(raw, "table", 400) or "",
            sql=_text(raw, "sql", 200_000),
            dax=raw.get("dax") is True,
            whole=raw.get("whole") is not False,
            extra=extra,
        )
    if kind == "file":
        path, absolute = _text(raw, "path"), _text(raw, "absolute")
        if not path and not absolute:
            raise SabError("A table's source names no file.")
        return Source(kind, path=path, absolute=absolute, sheet=_text(raw, "sheet", 200), extra=extra)
    if kind == "cell":
        notebook = _text(raw, "notebook")
        if not notebook:
            raise SabError("A table's source names no notebook.")
        return Source(kind, notebook=check_entry(notebook), extra=extra)
    if kind == "query":
        sql = _text(raw, "sql", 200_000)
        if not sql:
            raise SabError("A table's source has no query.")
        return Source(kind, sql=sql, extra=extra)
    return Source("pasted", rows=raw.get("rows") is True, extra=extra)


def _flavour(path: str) -> Any:
    """Windows' path rules for a Windows path (a drive, a backslash), else POSIX's."""
    return ntpath if _DRIVE.match(path) or ("\\" in path and "/" not in path) else posixpath


def _kind(path: str) -> str:
    """notebook, script or app by the file's ending; "" for any other file."""
    try:
        return notebooks.kind_of(path)
    except notebooks.NotebookError:
        return ""


def _base(path: str) -> str:
    return re.split(r"[\\/]", path.rstrip("\\/"))[-1]


def near(path: str, folder: str | None) -> str | None:
    """`path` relative to `folder` (forward slashes) when it is inside it; else None."""
    if not folder:
        return None
    rules = _flavour(path)
    if rules is not _flavour(folder):
        return None
    try:
        full, root = rules.normpath(path), rules.normpath(folder)
        relative = rules.relpath(full, root)
    except ValueError:
        return None  # another drive
    if relative == "." or relative.startswith("..") or rules.isabs(relative):
        return None
    return str(relative).replace("\\", "/")


def candidates(source: Source, folder: str | None) -> list[str]:
    """Where a file source may be now: beside the .sab (its relative path) first, then where it was."""
    found: list[str] = []
    if source.path:
        rules = _flavour(source.path)
        if rules.isabs(source.path) or _DRIVE.match(source.path):
            found.append(source.path)
        elif folder:
            parts = source.path.split("/")
            found.append(_flavour(folder).join(folder, *parts))
    if source.absolute and source.absolute not in found:
        found.append(source.absolute)
    return found


def source_of(
    origin: Origin,
    sab_folder: str | None,
    project_folder: str | None,
    kernel_document: str | None,
    place: tuple[str, str, str] | None,
    whole: bool,
    rows: bool,
) -> Source:
    """What the file says about a table that came from `origin`. `kernel_document`: the Workbench
    document whose kernel pushed it; `place`: a connection's database, schema and table."""
    if origin.kind == "file" and origin.path:
        relative = near(origin.path, sab_folder)
        return Source("file", path=relative or origin.path, absolute=origin.path, sheet=origin.sheet)
    if origin.kind == "connection" and origin.connection and place is not None:
        database, schema, table = place
        # A Power BI workspace names its dataset too ("Finance/Sales model"): the connection is the first.
        name = origin.connection.split("/", 1)[0] if origin.dax else origin.connection
        sql = origin.sql if origin.dax else None
        return Source("connection", connection=name, database=database, schema=schema, table=table,
                      sql=sql, dax=origin.dax, whole=whole)  # fmt: skip
    if origin.kind == "connection" and origin.connection and origin.sql and place is None:
        # A query of the user's on a connection (a table's connection swapped): read again by its query.
        # DAX: on the dataset its name holds (Finance/Sales model), kept as the schema.
        name, _, dataset = origin.connection.partition("/")
        return Source("connection", connection=name, schema=dataset if origin.dax else "", sql=origin.sql,
                      dax=origin.dax)  # fmt: skip
    if origin.kind == "query" and origin.sql:
        return Source("query", sql=origin.sql)
    if origin.kind == "python" and kernel_document:
        inside = near(kernel_document, project_folder)
        if inside is not None and _kind(inside) in ("notebook", "script"):
            return Source("cell", notebook=inside)
    return Source("pasted", rows=rows)


# ===== project.json =====


@dataclass(frozen=True)
class GridEntry:
    """One grid on a table: its steps and switches as the page sends them (checked when applied)."""

    steps: tuple[Mapping[str, Any], ...] = ()
    settings: Mapping[str, Any] = field(default_factory=dict)
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return dict(self.extra) | {"steps": [dict(s) for s in self.steps], "settings": dict(self.settings)}


@dataclass(frozen=True)
class TableEntry:
    name: str
    source: Source
    grids: tuple[GridEntry, ...] = (GridEntry(),)
    rows_file: str | None = None  # data/<table>.parquet, when its rows are in the file
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        out = dict(self.extra) | {
            "name": self.name,
            "source": self.source.to_json(),
            "grids": [g.to_json() for g in self.grids],
        }
        if self.rows_file:
            out["rows_file"] = self.rows_file
        return out


@dataclass(frozen=True)
class Manifest:
    name: str
    tables: tuple[TableEntry, ...] = ()
    app_version: str = ""
    saved: str = ""
    format: int = FORMAT
    tabs: Mapping[str, Any] = field(default_factory=dict)  # the home page: the tabs' order, the front one
    workbench: Mapping[str, Any] = field(default_factory=dict)  # the Workbench: documents, modes, layout
    diagram: Mapping[str, Any] = field(default_factory=dict)
    visualizations: str | None = None
    model: str | None = None
    autosave: bool = False  # saved quietly a short while after each change (the user's switch)
    extra: Mapping[str, Any] = field(default_factory=dict)

    def table(self, name: str) -> TableEntry | None:
        return next((t for t in self.tables if t.name == name), None)

    def special(self) -> set[str]:
        """The entries that are not the project's own files: the manifest, Visualizations, the model, rows."""
        named = {MANIFEST, *(t.rows_file for t in self.tables if t.rows_file)}
        return named | {n for n in (self.visualizations, self.model) if n}


_KNOWN = {
    "format",
    "app_version",
    "name",
    "saved",
    "tables",
    "tabs",
    "workbench",
    "diagram",
    "visualizations",
}
_KNOWN |= {"sandbox"}  # the old key: read as visualizations, not carried
_KNOWN |= {"model", "autosave", MARK_KEY}


def check_name(name: Any) -> str:
    """A project's name: one line, at most 100 characters, nothing a file system refuses."""
    said = name.strip() if isinstance(name, str) else ""
    if not said or len(said) > MAX_NAME or not re.fullmatch(r"[^\\/:*?\"<>|\x00-\x1f]+", said):
        raise SabError("A project's name is one line, at most 100 characters, with no \\ / : * ? \" < > |.")
    return said


def name_of_file(path: str) -> str:
    """A project's name from its file's: sales.sab -> sales."""
    stem = _base(path)
    return stem[: -len(SUFFIX)] if stem.lower().endswith(SUFFIX) else stem


def with_suffix(path: str) -> str:
    return path if path.lower().endswith(SUFFIX) else path + SUFFIX


def _mapping(raw: Any) -> dict[str, Any]:
    return dict(raw) if isinstance(raw, dict) else {}


def _grid(raw: Any) -> GridEntry:
    if not isinstance(raw, dict):
        return GridEntry()
    steps = raw.get("steps")
    return GridEntry(
        tuple(s for s in steps if isinstance(s, dict)) if isinstance(steps, list) else (),
        _mapping(raw.get("settings")),
        {k: v for k, v in raw.items() if k not in ("steps", "settings")},
    )


def _table(raw: Any) -> TableEntry | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not raw["name"].strip():
        return None
    grids = raw.get("grids")
    rows_file = raw.get("rows_file")
    return TableEntry(
        raw["name"],
        read_source(raw.get("source")),
        tuple(_grid(g) for g in grids) if isinstance(grids, list) else (GridEntry(),),
        check_entry(rows_file) if isinstance(rows_file, str) and rows_file else None,
        {k: v for k, v in raw.items() if k not in ("name", "source", "grids", "rows_file")},
    )


def read_manifest(text: str) -> tuple[Manifest, str | None]:
    """project.json, and why it opens read-only (None: it does not). Unknown fields are kept."""
    try:
        raw = json.loads(text)
    except ValueError:
        raise SabError("This file is not a project (its project.json is not JSON).") from None
    if not isinstance(raw, dict) or raw.get(MARK_KEY) != MARK:
        raise SabError("This file is not a Swiss Army Bench project.")
    version = raw.get("format")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise SabError("This project's format is not one this version reads.")
    read_only = None
    if version > FORMAT:
        writer = raw.get("app_version") if isinstance(raw.get("app_version"), str) else "a newer version"
        read_only = (
            f"This project was saved by {writer} in a newer format: it opens read-only here. "
            "Update to save it."
        )
    listed = raw.get("tables")
    tables: list[Any] = listed if isinstance(listed, list) else []
    read = [t for t in (_table(r) for r in tables[:MAX_TABLES]) if t is not None]
    names: set[str] = set()
    kept = []
    for table in read:  # one entry a name: the first one wins
        if table.name not in names:
            names.add(table.name)
            kept.append(table)

    def entry(key: str) -> str | None:
        value = raw.get(key)
        return check_entry(value) if isinstance(value, str) and value else None

    manifest = Manifest(
        name=raw["name"] if isinstance(raw.get("name"), str) and raw["name"].strip() else "Project",
        tables=tuple(kept),
        app_version=str(raw.get("app_version") or ""),
        saved=str(raw.get("saved") or ""),
        format=version,
        tabs=_mapping(raw.get("tabs")),
        workbench=_mapping(raw.get("workbench")),
        diagram=_mapping(raw.get("diagram")),
        visualizations=entry("visualizations") or entry("sandbox"),
        model=entry("model"),
        autosave=raw.get("autosave") is True,
        extra={k: v for k, v in raw.items() if k not in _KNOWN},
    )
    return manifest, read_only


def write_manifest(manifest: Manifest) -> str:
    """project.json's text. What an earlier read kept that this version does not know goes back in."""
    body: dict[str, Any] = dict(manifest.extra) | {
        MARK_KEY: MARK,
        "format": FORMAT,
        "app_version": manifest.app_version,
        "name": manifest.name,
        "saved": manifest.saved,
        "tables": [t.to_json() for t in manifest.tables],
        "tabs": dict(manifest.tabs),
        "workbench": dict(manifest.workbench),
        "diagram": dict(manifest.diagram),
        "visualizations": manifest.visualizations,
        "model": manifest.model,
        "autosave": manifest.autosave,
    }
    return json.dumps(body, indent=1, ensure_ascii=False, default=str) + "\n"


def carried(earlier: Manifest | None, name: str, table: TableEntry) -> TableEntry:
    """A table as it goes into the file again: what the earlier file kept of it that this version does
    not know (its own and its source's fields) goes back in."""
    before = earlier.table(name) if earlier is not None else None
    if before is None:
        return table
    source = table.source
    if before.source.kind == source.kind and before.source.extra:
        source = replace(source, extra=dict(before.source.extra) | dict(source.extra))
    return replace(table, source=source, extra=dict(before.extra) | dict(table.extra))


# ===== zip entries: checked before anything is unpacked =====


def check_entry(name: str) -> str:
    """A zip entry's name as a path inside the project: forward slashes, no `..`, no absolute path, no
    drive, no control character. Refused in words otherwise."""
    if not isinstance(name, str) or not name or len(name) > MAX_ENTRY_NAME or _CONTROL.search(name):
        raise SabError("The file holds an entry with a name that is not a plain path.")
    if "\\" in name or name.startswith("/") or _DRIVE.match(name):
        raise SabError(f"The file holds an entry outside the project ({name[:80]}): it was not opened.")
    parts = name.rstrip("/").split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise SabError(f"The file holds an entry outside the project ({name[:80]}): it was not opened.")
    return "/".join(parts)


@dataclass(frozen=True)
class EntryInfo:
    name: str
    size: int  # as the zip says (the reader counts again as it reads)
    link: bool  # a symbolic link (by its mode bits)
    folder: bool


def check_entries(entries: Sequence[EntryInfo], max_entries: int, max_total: int, max_entry: int) -> None:
    """Every entry's name and the sizes, before anything is written: refused in words."""
    if len(entries) > max_entries:
        raise SabError(f"The file holds over {max_entries:,} entries: it was not opened.")
    total = 0
    seen: set[str] = set()
    for entry in entries:
        name = check_entry(entry.name)
        if entry.link:
            raise SabError(f"The file holds a link ({name[:80]}): it was not opened.")
        if entry.folder:
            continue
        if name.casefold() in seen:
            raise SabError(f"The file holds {name[:80]} twice: it was not opened.")
        seen.add(name.casefold())
        if entry.size > max_entry:
            raise SabError(f"{name[:80]} is too large to open ({entry.size:,} bytes).")
        total += entry.size
        if total > max_total:
            raise SabError(f"The file unpacks to over {max_total:,} bytes: it was not opened.")
    if MANIFEST not in seen:
        raise SabError("This file is not a project (it has no project.json).")


# ===== which files go in =====


def packed(relative: str) -> bool:
    """A working folder's file that goes into the .sab (its path inside the project, forward slashes)."""
    parts = relative.split("/")
    if any(p in SKIPPED_FOLDERS or (p.startswith(".") and p != ".streamlit") for p in parts[:-1]):
        return False
    name = parts[-1]
    if name.startswith(".") or name.endswith(".saving"):
        return False
    lowered = name.lower()
    if lowered.endswith(".stapp.json"):
        return True
    return posixpath.splitext(lowered)[1] in PACKED_SUFFIXES


def rows_entry(table: str, taken: Iterable[str]) -> str:
    """data/<table>.parquet, or a name beside it when the project has a file of that name."""
    used = {t.casefold() for t in taken}
    name = f"{ROWS_FOLDER}/{table}.parquet"
    n = 2
    while name.casefold() in used:
        name = f"{ROWS_FOLDER}/{table}-{n}.parquet"
        n += 1
    return name


def for_the_file(path: str, text: str) -> str:
    """A notebook or script as it goes into the .sab: its outputs dropped (they show rows) and a pasted
    table's rows written out in its read-only cell taken out: rows go in only on a tick, as Parquet."""
    kind = _kind(path)
    if kind == "script":
        return project_rules.script_without_rows(text)
    if kind != "notebook":
        return text
    cells, following = notebooks.read_document(text)
    kept = project_rules.without_rows([DataCell(c.kind, c.source, c.role, c.table, c.number) for c in cells])
    for cell, data in zip(cells, kept, strict=True):
        cell.source = data.source
        cell.outputs = []
        cell.execution_count = None
        if cell.approved is not None:
            cell.approved = approvals.without_rows(cell.approved)
    return notebooks.write_notebook(cells, next_number=following)


# ===== a table that could not come back: its state and its fix =====


def _fix(table: str, state: str, message: str, kind: str, label: str, **more: Any) -> dict[str, Any]:
    return {"table": table, "state": state, "message": message, "fix": {"kind": kind, "label": label, **more}}


def fix_for(table: str, source: Source, problem: str) -> dict[str, Any]:
    """What the page shows for a table that is not back, and the one click that fixes it (never a dead
    end). `problem`: no_connection, no_file, not_run, no_rows, or what went wrong in words."""
    if problem == "no_connection":
        name = source.connection or ""
        message = f"No connection {name} on this computer"
        return _fix(table, problem, message, "add_connection", f"Add connection {name}", connection=name)
    if problem == "needs_password":
        name = source.connection or ""
        message = f"{name} needs a password on this computer"
        return _fix(table, problem, message, "password", "Set the password", connection=name)
    if problem == "no_file":
        name = source.label() or table
        suffix = posixpath.splitext(name.lower())[1]
        return _fix(table, problem, f"{name} is not where it was", "find_file", f"Find {name}",
                    file=name, suffix=suffix)  # fmt: skip
    if problem == "not_run":
        name = source.label()
        return _fix(
            table, problem, f"Made by {name}", "open_notebook", f"Open {name}", notebook=source.notebook
        )
    if problem == "no_rows":
        return _fix(table, problem, "Its rows were not kept in the file", "remove", "Remove")
    return _fix(table, "failed", problem[:300], "retry", "Try again")
