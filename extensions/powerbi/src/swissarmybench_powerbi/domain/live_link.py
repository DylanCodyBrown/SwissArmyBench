"""Edit in Power BI Desktop: the live link (the owner, 2026-11-19: "Editing = the live Power BI Desktop link
only"). It is NOT a connection kind and never reads a .pbix file (domain/pbix_file.py is the other path).
Windows
only: Power BI Desktop runs only there.

  [FIND]    each running Desktop's Analysis Services instance: its port (msmdsrv.port.txt, UTF-16) under the
            user's AnalysisServicesWorkspaces (the installer's and the Microsoft Store's places), and the
            file it
            has open (the Desktop process's command line); the status words ("Live: Sales.pbix" / "Not open:
            open Sales.pbix in Power BI Desktop")
  [MODEL]   the open model's metadata as names (tables, columns, measures, relationships): never rows
  [EDITS]   what an external tool may change, as Microsoft Learn's "External tools in Power BI Desktop" says
            (https://learn.microsoft.com/power-bi/transform-model/desktop-external-tools#data-modeling-operations,
            read 2026-11-19): write operations on the model's metadata are supported (measures with their
            format
            strings, calculated columns and tables, relationships, calculation groups); processing commands
            are
            not, a .pbit is not, and Power BI's own automatic date tables are not to be changed. Anything else
            points to the Power BI Project export. A dry run lists each change in words before any is made

Pure rules: standard library only, no I/O.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

DISCOVERY_SECONDS = 15  # a setting (10-15 s): how often the running Desktops are looked for
WINDOWS_ONLY = "Edit in Power BI Desktop runs on Windows, where Power BI Desktop runs."
LOCAL_ONLY = (
    "Only works on your machine: Power BI Desktop runs only here. On a Function App or hosted Streamlit app "
    "use "
    "the published dataset."
)
EXPORT_INSTEAD = "export a Power BI Project instead."
KINDS = (
    "measure_add",
    "measure_change",
    "measure_delete",
    "relationship_add",
    "relationship_delete",
    "calculated_column",
    "calculated_table",
    "calculation_group",
)
REFUSED = {
    "refresh": "processing (a refresh) is not supported from an external tool",
    "partition": "a table's Power Query is changed in Power BI Desktop or its Power BI Project",
    "data_source": "a source is changed in Power BI Desktop or the Power BI Project",
}
_AUTO = re.compile(r"^(LocalDateTable_|DateTableTemplate_)")


class LiveError(ValueError):
    """An edit that cannot be made as asked; the message says why."""


# ===== finding the running Desktops =====


def port_of(data: bytes) -> int | None:
    """msmdsrv.port.txt's port (Power BI Desktop writes it in UTF-16 LE; a plain one is read too)."""
    for encoding in ("utf-16-le", "utf-8"):
        try:
            text = data.decode(encoding).strip().lstrip("﻿").strip("\x00").strip()
        except UnicodeDecodeError:
            continue
        if text.isdigit() and 0 < int(text) < 65536:
            return int(text)
    return None


def file_of(command_line: str) -> str:
    """The .pbix (or .pbip) a Desktop process's command line opened: the last argument ending so."""
    found = re.findall(r'"([^"]+\.pbi[xp])"|(\S+\.pbi[xp])\b', command_line or "", re.IGNORECASE)
    paths = [a or b for a, b in found]
    return paths[-1] if paths else ""


@dataclass(frozen=True)
class Instance:
    port: int
    workspace: str  # its AnalysisServicesWorkspaces folder
    file: str = ""  # the open .pbix's path ("" while unknown: a new, unsaved file)

    @property
    def name(self) -> str:
        return re.split(r"[\\/]", self.file)[-1] if self.file else ""

    def to_json(self) -> dict[str, Any]:
        return {"port": self.port, "file": self.file, "name": self.name}


def matching(instances: Iterable[Instance], target: str) -> Instance | None:
    """The running Desktop that has the project's target open (by its file name, any case)."""
    wanted = re.split(r"[\\/]", target or "")[-1].casefold()
    return next((i for i in instances if wanted and i.name.casefold() == wanted), None)


def status_words(instances: Sequence[Instance], target: str, windows: bool = True) -> dict[str, Any]:
    if not windows:
        return {"live": False, "words": WINDOWS_ONLY}
    name = re.split(r"[\\/]", target or "")[-1]
    found = matching(instances, target)
    if found is not None:
        return {"live": True, "words": f"Live: {found.name}", "port": found.port}
    return {"live": False, "words": f"Not open: open {name} in Power BI Desktop" if name else "Not open"}


# ===== the open model's metadata (names only) and our changes to it =====


@dataclass(frozen=True)
class Change:
    kind: str
    table: str = ""
    name: str = ""
    expression: str = ""
    format: str = ""
    folder: str = ""
    to_table: str = ""
    to_column: str = ""
    column: str = ""
    active: bool = True
    items: tuple[tuple[str, str], ...] = ()  # a calculation group's items: (name, expression)

    def words(self) -> str:
        if self.kind == "measure_add":
            return f"Add the measure {self.table}[{self.name}]"
        if self.kind == "measure_change":
            return f"Change the measure {self.table}[{self.name}]"
        if self.kind == "measure_delete":
            return f"Delete the measure {self.table}[{self.name}]"
        if self.kind == "relationship_add":
            state = "" if self.active else " (inactive)"
            ends = f"{self.table}[{self.column}] to {self.to_table}[{self.to_column}]"
            return f"Add the relationship {ends}{state}"
        if self.kind == "relationship_delete":
            return f"Delete the relationship {self.table}[{self.column}] to {self.to_table}[{self.to_column}]"
        if self.kind == "calculated_column":
            return f"Add the calculated column {self.table}[{self.name}]"
        if self.kind == "calculated_table":
            return f"Add the calculated table {self.name}"
        return f"Add the calculation group {self.name} ({len(self.items)} items)"

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind, "words": self.words()}
        for key in ("table", "name", "expression", "format", "folder", "to_table", "to_column", "column"):
            if getattr(self, key):
                out[key] = getattr(self, key)
        if self.kind.startswith("relationship"):
            out["active"] = self.active
        if self.items:
            out["items"] = [{"name": n, "expression": e} for n, e in self.items]
        return out


def change_from(raw: Any) -> Change:
    """One change as sent ({kind, table, name, expression, ...}); a refused kind says why and what instead."""
    if not isinstance(raw, Mapping):
        raise LiveError("Send each change as {kind, table, name, ...}.")
    kind = str(raw.get("kind") or "")
    if kind in REFUSED:
        raise LiveError(f"{REFUSED[kind][0].upper()}{REFUSED[kind][1:]}: {EXPORT_INSTEAD}")
    if kind not in KINDS:
        raise LiveError(f"{kind or 'That'} is not a change here ({', '.join(KINDS)}): {EXPORT_INSTEAD}")
    items = tuple(
        (str(i.get("name", "")), str(i.get("expression", "")))
        for i in raw.get("items") or []
        if isinstance(i, Mapping)
    )
    change = Change(
        kind,
        str(raw.get("table") or ""),
        str(raw.get("name") or ""),
        str(raw.get("expression") or ""),
        str(raw.get("format") or ""),
        str(raw.get("folder") or ""),
        str(raw.get("to_table") or ""),
        str(raw.get("to_column") or ""),
        str(raw.get("column") or ""),
        raw.get("active") is not False,
        items,
    )
    for table in (change.table, change.to_table, change.name if kind == "calculated_table" else ""):
        if _AUTO.match(table):
            raise LiveError(f"{table} is Power BI's own date table: external tools may not change it.")
    return change


@dataclass
class OpenModel:
    """The open model's metadata, as the live link reads it: names only."""

    tables: dict[str, list[str]] = field(default_factory=dict)  # table -> its columns
    measures: dict[tuple[str, str], str] = field(default_factory=dict)  # (table, name) -> expression
    relationships: list[tuple[str, str, str, str, bool]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "tables": [{"name": t, "columns": c} for t, c in self.tables.items() if not _AUTO.match(t)],
            "measures": [{"table": t, "name": n, "expression": e} for (t, n), e in self.measures.items()],
            "relationships": [
                {"from_table": a, "from_column": b, "to_table": c, "to_column": d, "active": e}
                for a, b, c, d, e in self.relationships
            ],
        }


def check(model: OpenModel, changes: Sequence[Change]) -> list[dict[str, Any]]:
    """The dry run: each change in words, and whether it can go (`ok`) or why not."""
    out: list[dict[str, Any]] = []
    for c in changes:
        why = ""
        if c.kind in ("measure_add", "calculated_column") and c.table not in model.tables:
            why = f"the open model has no table {c.table}"
        elif c.kind == "measure_add" and (c.table, c.name) in model.measures:
            why = "it is there already: change it instead"
        elif c.kind in ("measure_change", "measure_delete") and (c.table, c.name) not in model.measures:
            why = "the open model has no such measure"
        elif c.kind == "relationship_add":
            for table, column in ((c.table, c.column), (c.to_table, c.to_column)):
                if column not in model.tables.get(table, []):
                    why = f"the open model has no column {table}[{column}]"
            if any(
                (a, b, cc, d) == (c.table, c.column, c.to_table, c.to_column)
                for a, b, cc, d, _ in model.relationships
            ):
                why = "it is there already"
        elif c.kind in ("calculated_table", "calculation_group") and c.name in model.tables:
            why = f"a table {c.name} is there already"
        out.append(c.to_json() | {"ok": not why} | ({"why": why} if why else {}))
    return out


def ours(
    relationships: Iterable[Mapping[str, Any]], measures: Iterable[Mapping[str, Any]], model: OpenModel
) -> list[Change]:
    """Our relationships and measures (the project's model, its kept measures) as changes to the open one."""
    out: list[Change] = []
    for r in relationships:
        out.append(
            Change(
                "relationship_add",
                str(r["from_table"]),
                column=str(r["from_column"]),
                to_table=str(r["to_table"]),
                to_column=str(r["to_column"]),
                active=bool(r.get("active", True)),
            )
        )
    for m in measures:
        key = (str(m["table"]), str(m["name"]))
        if model.measures.get(key) == m.get("expression"):
            continue
        kind = "measure_change" if key in model.measures else "measure_add"
        out.append(
            Change(
                kind,
                key[0],
                key[1],
                str(m.get("expression", "")),
                str(m.get("format", "")),
                str(m.get("folder", "")),
            )
        )
    present = {(a, b, c, d) for a, b, c, d, _ in model.relationships}
    return [
        c
        for c in out
        if c.kind != "relationship_add" or (c.table, c.column, c.to_table, c.to_column) not in present
    ]
