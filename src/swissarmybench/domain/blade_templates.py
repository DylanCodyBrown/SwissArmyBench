"""A starter connection or blade (the starters themselves: server/blade_templates.py): the code a
connection's form or New blade starts from, and, for a connection, the query that lists its tables.
Standard library only; re-exported by domain/blades.py."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# The built-in starter pack every install has (src/swissarmybench/starters/): read-only, Copy as your own, and
# brought up to date by each new version of the app. Its families, in the order the blade list shows.
STARTERS = "Swiss Army Bench starters"
FAMILIES: tuple[str, ...] = (
    "Power BI",
    "Dataverse",
    "SharePoint",
    "Excel",
    "Files",
    "DAX",
    "HTML",
    "Markdown",
    "Streamlit",
    "Controllers",
    "Text and layout",
    "Components",
    "Write",
)
# Starters of other families listed in the Write family too (docs/ideas.md, "Writing data"): Excel's
# writers, and Power BI's refreshes (after the source is written, the model is refreshed).
CROSS_LISTED: dict[str, tuple[str, ...]] = {
    "Write": (
        "Excel make a workbook",
        "Power BI refresh dataset",
        "Power BI refresh and wait",
    ),
}

# Starters that went with the one Excel module (2026-11-22, Plans/excel.plan.md): the twelve cell-level Excel
# starters. Each old name answers with one line for one release: where its effect is now.
_MAKE = 'a design option of sab.blade("Excel make a workbook")'
GONE_STARTERS: dict[str, str] = {
    "Excel add sheet": 'a sheet of rows is sab.blade("Write to an Excel sheet"); a laid-out one is ' + _MAKE,
    "Excel set cell values": "a title or text block, " + _MAKE,
    "Excel write table": "a table block, " + _MAKE,
    "Excel borders": "a table's style, " + _MAKE,
    "Excel fonts and fills": "a block's style, " + _MAKE,
    "Excel number formats": "a column's format, " + _MAKE,
    "Excel autofit columns": "done for every table (a column's width sets it), " + _MAKE,
    "Excel freeze panes": "a sheet's freeze, " + _MAKE,
    "Excel merge cells": "a text block's w and h, " + _MAKE,
    "Excel conditional colours": "a table's conditional rules, " + _MAKE,
    "Excel range as table": "a table block with filter, " + _MAKE,
    "Excel copy template": 'sab.blade("Excel fill a template")',
}


def gone_starter(name: str) -> str | None:
    """The one line an old starter's name answers with (None: not one that went)."""
    for old, now in GONE_STARTERS.items():
        if old.casefold() == name.strip().casefold():
            return f"{old} went with the one Excel module: it is now {now}."
    return None


@dataclass(frozen=True)
class Template:
    id: str
    label: str
    group: str  # "Databases", "Files", "Vaults", "Other"
    kind: str  # "sql", "other", "vault" or "analysis"
    code: str
    variable: str
    dialect: str = "other"
    catalog_language: str | None = None  # "sql" or "python"
    catalog_command: str | None = None
    vault_mapping: tuple[tuple[str, str], ...] = ()  # (environment variable, secret name) examples
    note: str = ""
    # Ways to sign in, each its own code (the form's Sign in): (label, a text only that code holds, code).
    # The first is `code`.
    sign_ins: tuple[tuple[str, str, str], ...] = ()
    # Where the form first offers its passwords from: "vault" (a key vault), else saved on this computer.
    secrets_from: str = ""
    # A connection from the user's own Python: its Read a table box.
    read_command: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "group": self.group,
            "kind": self.kind,
            "dialect": self.dialect,
            "code": self.code,
            "variable": self.variable,
            "catalog": (
                {"language": self.catalog_language, "command": self.catalog_command}
                if self.catalog_language and self.catalog_command
                else None
            ),
            "vault_mapping": [{"env": e, "secret": s} for e, s in self.vault_mapping],
            "note": self.note,
            "sign_ins": [{"label": label, "mark": mark, "code": code} for label, mark, code in self.sign_ins],
            "secrets_from": self.secrets_from,
            "read": {"command": self.read_command} if self.read_command else None,
        }
