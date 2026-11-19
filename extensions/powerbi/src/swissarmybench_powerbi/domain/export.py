"""The model as a Power BI Project (.pbip), the documented text format Power BI Desktop opens (the owner,
2026-11-19: "Make a powerbi desktop file with our model exported an option on the erd page"). The Microsoft
pages followed are in docs/verified.md ("Export to Power BI").

  [TYPES]          a DuckDB type -> Power BI's (int64, double, decimal, string, dateTime, boolean); anything
                   else string, said
  [RELATIONSHIPS]  the current model's joins between the tables going: one column each side, the same type on
                   both (else left out, said), many-to-one / one-to-one / many-to-many, single cross-filter;
                   Power BI refuses two active paths between two tables, so the strongest (the Key Finder's
                   score in its evidence, then the order) stays active and the others are made inactive, said
  [FILES]          <Name>.pbip, <Name>.SemanticModel/ (definition.pbism; definition/ in TMDL: database, model,
                   relationships, expressions, tables/<table>.tmdl) and <Name>.Report/ (definition.pbir by
                   path; the smallest report: one empty page). Every file's bytes come from the model alone:
                   sorted, CRLF as Power BI Desktop writes, lineage tags derived from names (uuid5), no
                   timestamps

Pure rules: standard library only (the M is domain/power_query.py's), no I/O.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from swissarmybench.domain.relationships import Relationship
from swissarmybench_powerbi.domain.power_query import MText, parameter_line

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{0,63}$")
FOLDER: str = "powerbi"  # inside the open project
DATA_FOLDER_PARAMETER: str = "DataFolder"
COMPATIBILITY_LEVEL: int = 1600
PAGE: str = "a1b2c3d4e5f6a7b8c9d0"  # the one empty page's name (20 characters, as Power BI names them)
EOL = "\r\n"  # Power BI Desktop's end of line
_LINEAGE = uuid.UUID("5a1b0b3e-8c1f-4f0e-9d2a-6b7c8d9e0f10")  # the namespace every lineage tag is made in
GITIGNORE: str = "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n**/*.SemanticModel/data/\n"

# The Microsoft schemas each file names (docs/verified.md).
PBIP_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json"
PBISM_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json"
PBIR_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json"
)
VERSION_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json"
REPORT_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.1.0/schema.json"
)
PAGES_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json"
PAGE_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json"
)
BASE_THEME = "CY25SU12"  # the base theme Microsoft's report.json example names (shipped with Power BI)
THEME_VERSION = {"visual": "2.5.0", "report": "3.1.0", "page": "2.3.0"}


class PowerBIExportError(ValueError):
    """An export that cannot be made as asked; the message says why."""


def check_name(name: Any) -> str:
    if not isinstance(name, str) or not NAME.match(name.strip()):
        raise PowerBIExportError(
            "A name is 1 to 64 letters, digits, spaces, '_' or '-', starting with a letter or digit."
        )
    return name.strip()


# ===== types =====

_INTEGER = re.compile(r"^(TINYINT|SMALLINT|INTEGER|INT|BIGINT|UTINYINT|USMALLINT|UINTEGER|INT[1248])$")


def data_type(duckdb_type: str) -> tuple[str, bool]:
    """Power BI's data type for a DuckDB type, and whether it was a fallback (said: "as text")."""
    t = duckdb_type.strip().upper()
    if _INTEGER.match(t):
        return "int64", False
    if t in ("DOUBLE", "FLOAT", "REAL", "FLOAT8", "FLOAT4"):
        return "double", False
    if t.startswith("DECIMAL") or t.startswith("NUMERIC"):
        return "decimal", False
    if t in ("VARCHAR", "TEXT", "STRING", "CHAR", "BPCHAR") or t.startswith("VARCHAR"):
        return "string", False
    if t == "DATE" or t.startswith("TIMESTAMP") or t == "DATETIME":
        return "dateTime", False
    if t in ("BOOLEAN", "BOOL"):
        return "boolean", False
    return "string", True


# ===== names and tags =====


def tmdl_name(name: str) -> str:
    """A TMDL object name: in single quotes (a quote doubled) unless it is a plain identifier."""
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return name
    return "'" + name.replace("'", "''") + "'"


def lineage_tag(*parts: str) -> str:
    """The same tag for the same object, every export (Power BI keeps an object's identity by it)."""
    return str(uuid.uuid5(_LINEAGE, "/".join(parts)))


# ===== relationships =====


@dataclass(frozen=True)
class Planned:
    relationship: Relationship
    active: bool = True
    left_out: str = ""  # why it does not go (empty: it goes)
    note: str = ""  # made inactive: why

    def to_json(self) -> dict[str, Any]:
        r = self.relationship
        return {
            "from": r.from_table,
            "from_columns": list(r.from_columns),
            "to": r.to_table,
            "to_columns": list(r.to_columns),
            "kind": r.kind,
            "goes": not self.left_out,
            "active": self.active and not self.left_out,
            **({"left_out": self.left_out} if self.left_out else {}),
            **({"note": self.note} if self.note else {}),
        }


def _strength(r: Relationship) -> float:
    found = re.search(r"(\d+(?:\.\d+)?)\s*%", r.evidence or "")
    return float(found.group(1)) if found else -1.0


def plan_relationships(
    relationships: Iterable[Relationship], columns: Mapping[str, Mapping[str, str]]
) -> list[Planned]:
    """Each relationship of the model between the tables going (`columns`: table -> column -> Power BI type):
    going or left out (and why); the active ones form no second path between two tables."""
    planned: list[Planned] = []
    for r in relationships:
        if r.from_table not in columns or r.to_table not in columns:
            continue
        why = ""
        if len(r.from_columns) != 1 or len(r.to_columns) != 1:
            why = "Power BI joins on one column each side; this join has several"
        else:
            a = columns[r.from_table].get(r.from_columns[0])
            b = columns[r.to_table].get(r.to_columns[0])
            if a is None or b is None:
                gone = r.from_columns[0] if a is None else r.to_columns[0]
                why = f"{gone} is not a column of the table as it goes"
            elif a != b:
                why = f"its two columns' types differ ({a} and {b}): make them the same in the grid"
        planned.append(Planned(r, left_out=why))
    # The one-active-path rule: strongest first (then as the model has them, an inactive join last).
    order = sorted(
        (i for i, p in enumerate(planned) if not p.left_out),
        key=lambda i: (not planned[i].relationship.active, -_strength(planned[i].relationship), i),
    )
    parent: dict[str, str] = {}

    def root(t: str) -> str:
        while parent.get(t, t) != t:
            t = parent[t]
        return t

    for i in order:
        r = planned[i].relationship
        a, b = root(r.from_table), root(r.to_table)
        if a == b:
            planned[i] = Planned(
                r, active=False, note="inactive: Power BI keeps one active path between two tables"
            )
        else:
            parent[a] = b
    return planned


# ===== the model's text =====


@dataclass(frozen=True)
class Measure:
    table: str
    name: str
    expression: str
    format_string: str = ""
    display_folder: str = ""
    description: str = ""


@dataclass(frozen=True)
class ExportTable:
    name: str
    columns: tuple[tuple[str, str], ...]  # (column, Power BI data type)
    m: MText
    keys: frozenset[str] = frozenset()  # columns a key or a join names: summarizeBy none


@dataclass(frozen=True)
class Package:
    files: dict[str, bytes] = field(default_factory=dict)  # path under the export's folder -> bytes


def _lines(lines: Iterable[str]) -> bytes:
    return (EOL.join(lines) + EOL).encode("utf-8")


def _json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False).replace("\n", EOL) + EOL).encode("utf-8")


def _expression(text: str, depth: int) -> list[str]:
    """A multi-line expression, indented as Power BI Desktop writes it (two tabs past its property)."""
    pad = "\t" * depth
    return [pad + line if line.strip() else "" for line in text.splitlines()]


def table_tmdl(table: ExportTable, measures: Sequence[Measure] = ()) -> bytes:
    name = tmdl_name(table.name)
    out = [f"table {name}", f"\tlineageTag: {lineage_tag('table', table.name)}", ""]
    for m in sorted(measures, key=lambda m: m.name.casefold()):
        if m.description:
            out += [f"\t/// {line}" for line in m.description.splitlines()]
        body = m.expression.strip()
        if "\n" in body:
            out += [f"\tmeasure {tmdl_name(m.name)} =", *_expression(body, 3)]
        else:
            out.append(f"\tmeasure {tmdl_name(m.name)} = {body}")
        if m.format_string:
            out.append(f"\t\tformatString: {_value(m.format_string)}")
        if m.display_folder:
            out.append(f"\t\tdisplayFolder: {_value(m.display_folder)}")
        out += [f"\t\tlineageTag: {lineage_tag('measure', table.name, m.name)}", ""]
    for column, kind in table.columns:
        numeric = kind in ("int64", "double", "decimal")
        summarize = "sum" if numeric and column not in table.keys else "none"
        out += [
            f"\tcolumn {tmdl_name(column)}",
            f"\t\tdataType: {kind}",
            f"\t\tlineageTag: {lineage_tag('column', table.name, column)}",
            f"\t\tsummarizeBy: {summarize}",
            f"\t\tsourceColumn: {_value(column)}",
            "",
            "\t\tannotation SummarizationSetBy = Automatic",
            "",
        ]
    out += [f"\tpartition {name} = m", "\t\tmode: import", "\t\tsource =", *_expression(table.m.text, 4), ""]
    out.append("\tannotation PBI_ResultType = Table")
    return _lines(out)


def _value(text: str) -> str:
    """A TMDL property value: in double quotes (doubled inside) when it has spaces at its ends or quotes."""
    if text != text.strip() or '"' in text or not text:
        return '"' + text.replace('"', '""') + '"'
    return text


def relationships_tmdl(planned: Sequence[Planned]) -> bytes | None:
    out: list[str] = []
    for p in planned:
        if p.left_out:
            continue
        r = p.relationship
        many, one = (r.from_table, r.from_columns[0]), (r.to_table, r.to_columns[0])
        if r.kind == "one-to-many":
            many, one = one, many
        key = f"{many[0]}.{many[1]}->{one[0]}.{one[1]}"
        out.append(f"relationship {lineage_tag('relationship', key)}")
        if not p.active:
            out.append("\tisActive: false")
        if r.kind == "one-to-one":
            out.append("\tfromCardinality: one")
        if r.kind == "many-to-many":
            out.append("\ttoCardinality: many")
        out += [
            f"\tfromColumn: {tmdl_name(many[0])}.{tmdl_name(many[1])}",
            f"\ttoColumn: {tmdl_name(one[0])}.{tmdl_name(one[1])}",
            "",
        ]
    return _lines(out[:-1]) if out else None


def expressions_tmdl(parameters: Mapping[str, str]) -> bytes | None:
    out: list[str] = []
    for name in sorted(parameters):
        out += [
            f"expression {tmdl_name(name)} = {parameter_line(name, parameters[name])}",
            f"\tlineageTag: {lineage_tag('expression', name)}",
            "",
            "\tannotation PBI_ResultType = Text",
            "",
        ]
    return _lines(out[:-1]) if out else None


def model_tmdl(tables: Sequence[str], parameters: Iterable[str]) -> bytes:
    order = [*sorted(parameters), *tables]
    out = [
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tsourceQueryCulture: en-US",
        "\tdataAccessOptions",
        "\t\tlegacyRedirects",
        "\t\treturnErrorValuesAsNull",
        "",
        f"annotation PBI_QueryOrder = {json.dumps(order, ensure_ascii=False, separators=(',', ':'))}",
        "",
        "annotation __PBI_TimeIntelligenceEnabled = 0",
        "",
        'annotation PBI_ProTooling = ["DevMode"]',
        "",
        *[f"ref table {tmdl_name(t)}" for t in tables],
    ]
    return _lines(out)


def build(
    name: str,
    tables: Sequence[ExportTable],
    planned: Sequence[Planned],
    parameters: Mapping[str, str],
    measures: Sequence[Measure] = (),
    report: Mapping[str, bytes] | None = None,
) -> Package:
    """Every file of the export, by its path under the export's folder (`powerbi/` in a project). `report`:
    another report's files for <Name>.Report/ (the report swap); None: the smallest report, one empty page."""
    model = f"{name}.SemanticModel"
    definition = f"{model}/definition"
    ordered = sorted(tables, key=lambda t: t.name.casefold())
    files: dict[str, bytes] = {
        f"{name}.pbip": _json(
            {
                "$schema": PBIP_SCHEMA,
                "version": "1.0",
                "artifacts": [{"report": {"path": f"{name}.Report"}}],
                "settings": {"enableAutoRecovery": True},
            }
        ),
        f"{model}/definition.pbism": _json(
            {"$schema": PBISM_SCHEMA, "version": "5.0", "settings": {"qnaEnabled": False}}
        ),
        f"{definition}/database.tmdl": _lines(["database", f"\tcompatibilityLevel: {COMPATIBILITY_LEVEL}"]),
        f"{definition}/model.tmdl": model_tmdl([t.name for t in ordered], parameters),
    }
    for table in ordered:
        mine = [m for m in measures if m.table == table.name]
        files[f"{definition}/tables/{table.name}.tmdl"] = table_tmdl(table, mine)
    rel = relationships_tmdl(planned)
    if rel is not None:
        files[f"{definition}/relationships.tmdl"] = rel
    expr = expressions_tmdl(parameters)
    if expr is not None:
        files[f"{definition}/expressions.tmdl"] = expr
    files |= {f"{name}.Report/{path}": data for path, data in (report or smallest_report(name)).items()}
    return Package(files)


def smallest_report(name: str) -> dict[str, bytes]:
    """The smallest valid report (PBIR): its definition.pbir pointing at the model by its relative path, and
    one empty page."""
    return {
        "definition.pbir": pbir(name),
        "definition/version.json": _json({"$schema": VERSION_SCHEMA, "version": "2.0.0"}),
        "definition/report.json": _json(
            {
                "$schema": REPORT_SCHEMA,
                "themeCollection": {
                    "baseTheme": {
                        "name": BASE_THEME,
                        "reportVersionAtImport": THEME_VERSION,
                        "type": "SharedResources",
                    }
                },
                "resourcePackages": [
                    {
                        "name": "SharedResources",
                        "type": "SharedResources",
                        "items": [
                            {"name": BASE_THEME, "path": f"BaseThemes/{BASE_THEME}.json", "type": "BaseTheme"}
                        ],
                    }
                ],
            }
        ),
        "definition/pages/pages.json": _json(
            {"$schema": PAGES_SCHEMA, "pageOrder": [PAGE], "activePageName": PAGE}
        ),
        f"definition/pages/{PAGE}/page.json": _json(
            {
                "$schema": PAGE_SCHEMA,
                "name": PAGE,
                "displayName": "Page 1",
                "displayOption": "FitToPage",
                "height": 720,
                "width": 1280,
            }
        ),
    }


def pbir(name: str) -> bytes:
    return _json(
        {
            "$schema": PBIR_SCHEMA,
            "version": "4.0",
            "datasetReference": {"byPath": {"path": f"../{name}.SemanticModel"}},
        }
    )


def stale(name: str, existing: Iterable[str], package: Package) -> list[str]:
    """Files an earlier export left that this one does not write and Power BI would still read: a table no
    longer ticked (definition/tables/), rows no longer kept (data/), the earlier report's pages. Paths under
    the export's folder, '/' separated."""
    mine = (f"{name}.SemanticModel/definition/", f"{name}.SemanticModel/data/", f"{name}.Report/definition/")
    return sorted(p for p in existing if p.startswith(mine) and p not in package.files)
