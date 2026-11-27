"""A Power BI file (.pbix) read with pbixray: the one way a .pbix is READ (the owner, 2026-11-19: "Reading a
.pbix
= pbixray only. Editing = the live Power BI Desktop link only. They never cross"). Nothing here knows of a
running Power BI Desktop (domain/live_link.py is the other path), and nothing matches the two by a file's
name.

  [MODEL]       PbixModel: what pbixray tells of a file's model, as plain records (tables with their columns
                and each partition's M, relationships active or not, measures with their folders and formats,
                the Power Query parameters, when it was last refreshed), or a thin report: a .pbix with no
                model
                of its own, live-connected to a published dataset (its Connections part names it)
  [CONNECTION]  the .pbix file connection kind: a connection of your own Python (domain/python_connections.py:
                Connect, List the tables, Read a table) whose code reads the file with pbixray, so it lists
                its tables, reads one (only when a table is read) and DuckDB SQL names it like any connection;
                its path a box's text (`${NAME}` allowed: written into the code as os.environ["NAME"]); its
                tag
                `powerbi file`; read-only, and why; a path on this disk carries the amber note
  [WORDS]       "as of <last refresh>" on the card and the tree

Pure rules: standard library only, no I/O.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain import variable_refs as refs
from swissarmybench.domain.relationships import Relationship

TAG = "powerbi file"
TEMPLATE = "python"
SCHEMA = "model"  # every table of the file's one model is listed under this schema
KINDS: tuple[str, ...] = (".pbix",)
# The tables Power BI makes by itself for a date column (auto date/time): never listed.
_AUTO_TABLES = re.compile(r"^(LocalDateTable_|DateTableTemplate_)")
READ_ONLY = (
    "Read-only: a .pbix's rows are the copy Power BI kept at its last refresh; change the model in Power BI "
    "Desktop (Edit in Power BI Desktop) or export a Power BI Project"
)
LOCAL_PATH = (
    "Only works on your machine: it reads a .pbix on this computer's disk. On a Function App or hosted "
    "Streamlit "
    "app use the file in SharePoint or a lake (a path the app can reach), or the published dataset."
)


class PbixError(ValueError):
    """A .pbix that cannot be used as asked; the message says why in plain words."""


# ===== the model, as pbixray tells it =====


@dataclass(frozen=True)
class PColumn:
    name: str
    type: str = ""  # pbixray's pandas type name (int64, float64, string, datetime64[ns], bool, ...)


@dataclass(frozen=True)
class PTable:
    name: str
    columns: tuple[PColumn, ...] = ()
    m: str = ""  # its partition's Power Query (M), "" for a calculated table
    calculated: str = ""  # a calculated table's DAX


@dataclass(frozen=True)
class PRelationship:
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    active: bool = True
    cardinality: str = "many_to_one"
    both_ways: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "from_table": self.from_table,
            "from_column": self.from_column,
            "to_table": self.to_table,
            "to_column": self.to_column,
            "active": self.active,
            "cardinality": self.cardinality,
            "both_ways": self.both_ways,
        }


@dataclass(frozen=True)
class PMeasure:
    table: str
    name: str
    expression: str
    folder: str = ""
    format: str = ""
    description: str = ""

    def to_json(self) -> dict[str, str]:
        return {
            "table": self.table,
            "name": self.name,
            "expression": self.expression,
            "folder": self.folder,
            "format": self.format,
            "description": self.description,
        }


@dataclass(frozen=True)
class PbixModel:
    """A .pbix as read: its model, or (thin) the published dataset it is live-connected to."""

    name: str  # the file's name without .pbix
    tables: tuple[PTable, ...] = ()
    relationships: tuple[PRelationship, ...] = ()
    measures: tuple[PMeasure, ...] = ()
    parameters: Mapping[str, str] = field(default_factory=dict)  # Power Query parameter -> its value's text
    refreshed: str = ""  # its data's last refresh (ISO text), "" when the file does not say
    thin_dataset: str = ""  # a thin report: the published dataset's name
    thin_workspace: str = ""  # and its workspace's, when the connection string names it

    @property
    def thin(self) -> bool:
        return bool(self.thin_dataset)

    def table(self, name: str) -> PTable | None:
        wanted = name.casefold()
        return next((t for t in self.tables if t.name.casefold() == wanted), None)


def listed(tables: Iterable[PTable]) -> list[PTable]:
    """The tables a person sees: Power BI's own date tables left out."""
    return [t for t in tables if not _AUTO_TABLES.match(t.name)]


def as_of(refreshed: str) -> str:
    """The card's and tree's words for a file's rows: "as of 2026-11-02 14:05" (or "" when unknown)."""
    match = re.match(r"(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}))?", refreshed or "")
    if not match:
        return ""
    return "as of " + match.group(1) + (f" {match.group(2)}" if match.group(2) else "")


def m_parameter_value(expression: str) -> str:
    """A Power Query parameter's value from its expression: `"sql01" meta [IsParameterQuery=true, ...]`."""
    match = re.match(r'\s*"((?:[^"]|"")*)"', expression or "")
    if match:
        return match.group(1).replace('""', '"')
    number = re.match(r"\s*(-?\d+(?:\.\d+)?)", expression or "")
    return number.group(1) if number else ""


def thin_target(connections_json: str) -> tuple[str, str]:
    """A thin report's Connections part read: (dataset, workspace) it is live-connected to, else ("", "").

    The part is JSON: {"Connections": [{"ConnectionString": "Data Source=powerbi://api.powerbi.com/v1.0/myorg/
    Sales;Initial Catalog=Sales model;...", ...}], ...}."""
    try:
        data = json.loads(connections_json)
    except (ValueError, TypeError):
        return "", ""
    for connection in data.get("Connections", []) if isinstance(data, dict) else []:
        text = str(connection.get("ConnectionString") or "") if isinstance(connection, dict) else ""
        catalog = re.search(r"Initial Catalog=([^;]+)", text, re.IGNORECASE)
        source = re.search(r"Data Source=powerbi://[^;]*/myorg/([^;/]+)", text, re.IGNORECASE)
        if catalog:
            return catalog.group(1).strip().strip('"'), (source.group(1).strip() if source else "")
    return "", ""


# ===== the .pbix file connection: a Python connection that reads the file with pbixray =====


def path_code(path: str) -> str:
    """The file's path as Python: a literal, or os.environ["NAME"] for a `${NAME}` (joined with +)."""
    text = (path or "").strip()
    if not text:
        raise PbixError("Choose the .pbix file.")
    if not refs.holds(text) and not text.lower().endswith(".pbix"):
        raise PbixError("Use a .pbix file (a .pbit or .pbip has no rows to read).")
    pieces: list[str] = []
    for part in refs.parts(text):
        if isinstance(part, refs.Ref):
            pieces.append(f'os.environ["{part.name}"]')
        elif part:
            pieces.append(repr(part))
    return " + ".join(pieces) or "''"


def path_variables(path: str) -> list[str]:
    """The variables a path names (each `${NAME}`), in order."""
    return [p.name for p in refs.parts(path or "") if isinstance(p, refs.Ref)]


def connect_code(path: str) -> str:
    return (
        "import os\n\n"
        "from pbixray import PBIXRay  # reads a .pbix's model and the rows it kept at its last refresh\n\n"
        f"conn = PBIXRay({path_code(path)})"
    )


LIST_CODE = """[
    {"schema": "model", "table": str(row.TableName), "column": str(row.ColumnName), "type":
    str(row.PandasDataType)}
    for row in conn.schema.itertuples()
    if not str(row.TableName).startswith(("LocalDateTable_", "DateTableTemplate_"))
]"""

READ_CODE = """rows = conn.get_table(table)
(rows.head(limit) if limit else rows), len(rows)"""


def connection_body(name: str, path: str, variables: Sequence[Mapping[str, str]] = ()) -> dict[str, Any]:
    """What POST /connections takes for a .pbix file connection named `name` (a Python connection)."""
    if not str(name or "").strip():
        raise PbixError("Name the connection.")
    named = {str(v.get("name")): dict(v) for v in variables}
    return {
        "name": str(name).strip(),
        "kind": "other",
        "template": TEMPLATE,
        "variable": "conn",
        "code": connect_code(path),
        "catalog": {"language": "python", "command": LIST_CODE},
        "read": {"command": READ_CODE},
        "variables": [named.get(n, {"name": n, "from": "env"}) for n in path_variables(path)],
        "tags": [TAG],
        "description": f"A Power BI file read with pbixray: {path.strip()}",
    }


def is_pbix_connection(tags: Iterable[str]) -> bool:
    return TAG in {str(t).casefold() for t in tags}


def path_of(code: str) -> str:
    """A .pbix connection's path read back from its Connect code (a literal, or `${NAME}` text)."""
    match = re.search(r"PBIXRay\((.*)\)\s*$", code or "", re.MULTILINE)
    if not match:
        return ""
    out: list[str] = []
    for piece in match.group(1).split("+"):
        piece = piece.strip()
        env = re.fullmatch(r'os\.environ\["([A-Za-z_][A-Za-z0-9_]*)"\]', piece)
        if env:
            out.append("${" + env.group(1) + "}")
            continue
        try:
            value = ast.literal_eval(piece)
        except (ValueError, SyntaxError):
            continue
        if isinstance(value, str):
            out.append(refs.escape(value))
    return "".join(out)


def local_path(path: str) -> bool:
    """A path on this computer's disk (a drive, a home folder, an absolute or relative path; a `${NAME}` that
    could name anything is judged by the rest of the text)."""
    text = (path or "").strip()
    return not re.match(r"^(https?|abfss?|az)://", text, re.IGNORECASE)


def card(model: PbixModel | None, path: str, error: str = "") -> dict[str, Any]:
    """The card's and tree's facts: the path, its tables, "as of", read-only and why, the amber note."""
    out: dict[str, Any] = {
        "path": path,
        "read_only": READ_ONLY,
        "portability": LOCAL_PATH if local_path(path) else "",
    }
    if error:
        out["error"] = error
    if model is not None:
        out |= {
            "tables": [t.name for t in listed(model.tables)],
            "relationships": len(model.relationships),
            "measures": len(model.measures),
            "as_of": as_of(model.refreshed),
            "thin": model.thin_dataset,
        }
    return out


def relationships_for_model(model: PbixModel) -> list[Relationship]:
    """The file's relationships as the app's model takes them (the ERD), active or not kept."""
    out: list[Relationship] = []
    for r in model.relationships:
        if _AUTO_TABLES.match(r.from_table) or _AUTO_TABLES.match(r.to_table):
            continue
        kind = r.cardinality.replace("_", "-")
        out.append(
            Relationship(r.from_table, (r.from_column,), r.to_table, (r.to_column,), kind, active=r.active)
        )
    return out
