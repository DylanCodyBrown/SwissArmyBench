"""Use an existing report's pages (the owner, 2026-11-19: "an option to replace a current Power BI report's
model by dragging and dropping a pbix into the app"): another report's pages, visuals, themes and bookmarks
written into the export's <Name>.Report/, pointed at OUR semantic model. The dropped file is read, never
changed.

  [READ]     a .pbix or .pbit is a zip: its report part only (Report/Layout, the legacy JSON in UTF-16 LE, or
             a PBIR Report/definition/ folder; Report/StaticResources/ for themes and images), never DataModel
             (binary, undocumented: we replace it). A .pbit's DataModelSchema (JSON) gives its measures.
             Unsafe entries (an absolute path, `..`, a drive) refused; sizes capped. A .pbip's .Report folder
             and its SemanticModel's TMDL are read the same way (the adapter hands its files over)
  [FIELDS]   every table, column and measure the visuals, filters and slicers name: the Entity/Property
             references (a query's From aliases followed) and the queryRef "Table.Field" names, in the legacy
             layout's JSON-in-strings (config, filters, query, dataTransforms) as in PBIR's files
  [MAPPING]  each field matched to our model by name, any case; the dialog's list (matched ticked, a picker
             for the rest, "leave it": Power BI's own broken-field state)
  [REWRITE]  every reference rewritten to the chosen names (Entity, Property, queryRef, Name, and the
             report's own measures' DAX); the model's measures (a .pbit, a .pbip, a .pbix through pbixray)
             brought along rewritten the same way, a measure naming something unmapped said and not written

Pure rules: standard library only, no I/O.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

MAX_ENTRY_BYTES: int = 64 * 1024 * 1024  # one entry of the report part
MAX_TOTAL_BYTES: int = 256 * 1024 * 1024  # the report part in all
MAX_ENTRIES: int = 5_000
KINDS: tuple[str, ...] = (".pbix", ".pbit", ".pbip")
# The legacy layout's keys whose values are JSON held in a string.
_NESTED = frozenset({"config", "filters", "query", "dataTransforms"})
_PBIX_HELP = "Save it as a template in Power BI Desktop (File, Export, Power BI template) and drop the .pbit."


class ReportError(ValueError):
    """A report that cannot be used as asked; the message says why."""


# ===== reading the archive =====


def safe_entry(name: str) -> bool:
    """A zip entry's name that stays inside: no absolute path, no drive, no `..`, no backslash trickery."""
    if not name or name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name):
        return False
    parts = name.replace("\\", "/").split("/")
    return ".." not in parts and "" not in parts[:-1]


def wanted_entries(entries: Iterable[tuple[str, int]]) -> list[str]:
    """The entries to read from a .pbix/.pbit (name, uncompressed size): the report part and DataModelSchema;
    raises ReportError on an unsafe name or past the caps. DataModel itself is never read."""
    out: list[str] = []
    total = count = 0
    for name, size in entries:
        count += 1
        if count > MAX_ENTRIES:
            raise ReportError("The file holds too many parts to be a report.")
        if not safe_entry(name):
            raise ReportError(f"The file has an unsafe part ({name[:80]}): it is not read.")
        if name == "DataModelSchema" or name.startswith("Report/"):
            if size > MAX_ENTRY_BYTES:
                raise ReportError(f"{name} is too large to read.")
            total += size
            if total > MAX_TOTAL_BYTES:
                raise ReportError("The report part is too large to read.")
            out.append(name)
    return out


def _text(data: bytes) -> str:
    """A part's text: UTF-16 LE (the legacy Layout, DataModelSchema), else UTF-8; a byte order mark gone."""
    if data.startswith(b"\xff\xfe") or (len(data) > 1 and data[1:2] == b"\x00"):
        return data.decode("utf-16-le").lstrip("﻿")
    return data.decode("utf-8-sig")


@dataclass
class Report:
    """A report's part as we use it: its files relative to the Report folder ("report.json" for the legacy
    layout; "definition/..." for PBIR; "StaticResources/..."), and the model's measures when the file has
    them."""

    source: str  # pbix, pbit or pbip
    files: dict[str, bytes] = field(default_factory=dict)
    measures: list[dict[str, str]] | None = None  # None: the file's model could not be read
    measures_note: str = ""


def from_archive(kind: str, parts: Mapping[str, bytes]) -> Report:
    """A .pbix's or .pbit's report part (`parts`: the wanted entries' bytes)."""
    report = Report(kind)
    for name, data in parts.items():
        inner = name.removeprefix("Report/")
        if name == "Report/Layout":
            report.files["report.json"] = _text(data).encode("utf-8")
        elif inner.startswith(("definition/", "StaticResources/")):
            report.files[inner] = data
    if "report.json" not in report.files and not any(p.startswith("definition/") for p in report.files):
        raise ReportError("The file has no report pages (no Report/Layout and no Report/definition).")
    if "DataModelSchema" in parts:
        report.measures = schema_measures(json.loads(_text(parts["DataModelSchema"])))
    elif kind == "pbix":
        report.measures_note = _PBIX_HELP
    return report


def from_folder(files: Mapping[str, bytes], tmdl: Mapping[str, str]) -> Report:
    """A .pbip's .Report folder's files (relative to it) and its SemanticModel's TMDL (definition/ files)."""
    report = Report("pbip")
    for name, data in files.items():
        if name.startswith(("definition/", "StaticResources/")) or name == "report.json":
            report.files[name] = data
    if "report.json" not in report.files and not any(p.startswith("definition/") for p in report.files):
        raise ReportError("The project's report folder has no pages.")
    report.measures = tmdl_measures(tmdl)
    return report


def schema_measures(schema: Mapping[str, Any]) -> list[dict[str, str]]:
    """A .pbit's DataModelSchema measures: table, name, expression, format, folder."""
    out: list[dict[str, str]] = []
    for table in schema.get("model", {}).get("tables", []) or []:
        for m in table.get("measures", []) or []:
            expression = m.get("expression", "")
            if isinstance(expression, list):
                expression = "\n".join(str(x) for x in expression)
            out.append(
                {
                    "table": str(table.get("name", "")),
                    "name": str(m.get("name", "")),
                    "expression": str(expression),
                    "format": str(m.get("formatString", "") or ""),
                    "folder": str(m.get("displayFolder", "") or ""),
                }
            )
    return out


_TMDL_MEASURE = re.compile(r"^\tmeasure\s+('(?:[^']|'')+'|[^=\s]+)\s*=\s*(.*)$")


def _unquote(name: str) -> str:
    return name[1:-1].replace("''", "'") if name.startswith("'") else name


def tmdl_measures(tmdl: Mapping[str, str]) -> list[dict[str, str]]:
    """Measures from TMDL table files (definition/tables/*.tmdl): their name, DAX, format and folder."""
    out: list[dict[str, str]] = []
    for path in sorted(tmdl):
        if not path.startswith("definition/tables/"):
            continue
        lines = tmdl[path].replace("\r\n", "\n").split("\n")
        table = (
            _unquote(lines[0].removeprefix("table ").strip())
            if lines and lines[0].startswith("table ")
            else ""
        )
        i = 0
        while i < len(lines):
            found = _TMDL_MEASURE.match(lines[i])
            if not found:
                i += 1
                continue
            name, first = _unquote(found.group(1)), found.group(2).strip()
            body = [first] if first and first != "```" else []
            i += 1
            while i < len(lines) and lines[i].startswith("\t\t\t"):  # a multi-line expression, a level deeper
                if lines[i].strip() != "```":
                    body.append(lines[i][3:])
                i += 1
            props: dict[str, str] = {}
            while i < len(lines) and lines[i].startswith("\t\t") and not lines[i].startswith("\t\t\t"):
                key, _, value = lines[i].strip().partition(":")
                props[key.strip()] = value.strip().strip('"')
                i += 1
            out.append(
                {
                    "table": table,
                    "name": name,
                    "expression": "\n".join(body),
                    "format": props.get("formatString", ""),
                    "folder": props.get("displayFolder", ""),
                }
            )
    return out


def pbix_measures(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """A .pbix's measures as pbixray answers them (its dax_measures rows: TableName, Name, Expression,
    DisplayFolder; a format when it has one)."""
    return [
        {
            "table": str(r.get("TableName", "")),
            "name": str(r.get("Name", "")),
            "expression": str(r.get("Expression", "") or ""),
            "format": str(r.get("FormatString", "") or ""),
            "folder": str(r.get("DisplayFolder", "") or ""),
        }
        for r in rows
    ]


def unreadable_pbix(reason: str) -> str:
    return f"This .pbix could not be read ({reason}). {_PBIX_HELP}"


# ===== the fields a report names =====

Field = tuple[str, str]  # (table, column or measure)


def _walk(value: Any, visit: Callable[[Any], Any], key: str = "") -> Any:
    """Every JSON node, the legacy layout's JSON-in-strings opened and closed again; `visit` may replace a
    dict."""
    if isinstance(value, str) and key in _NESTED and value[:1] in ("{", "["):
        try:
            inner = json.loads(value)
        except ValueError:
            return value
        return json.dumps(_walk(inner, visit), ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return [_walk(v, visit, key) for v in value]
    if isinstance(value, dict):
        node = visit(value)
        return {k: _walk(v, visit, k) for k, v in node.items()}
    return value


def _aliases(node: Mapping[str, Any]) -> dict[str, str]:
    found = node.get("From")
    out: dict[str, str] = {}
    for item in found if isinstance(found, list) else []:
        if (
            isinstance(item, dict)
            and isinstance(item.get("Name"), str)
            and isinstance(item.get("Entity"), str)
        ):
            out[item["Name"]] = item["Entity"]
    return out


_FIELD_KINDS = ("Column", "Measure", "Aggregation", "HierarchyLevel")


def _ref(node: Mapping[str, Any], aliases: Mapping[str, str]) -> tuple[str, str, str] | None:
    """A {Column|Measure: {Expression: {SourceRef: {Entity|Source}}, Property}} node's kind, table, field."""
    for kind in ("Column", "Measure"):
        inner = node.get(kind)
        if isinstance(inner, dict) and isinstance(inner.get("Property"), str):
            source = (inner.get("Expression") or {}).get("SourceRef") or {}
            table = source.get("Entity") or aliases.get(str(source.get("Source", "")), "")
            if table:
                return kind.lower(), str(table), inner["Property"]
    return None


_QUERY_REF = re.compile(r"^(?:[A-Za-z]+\()?([^().]+)\.([^()]+?)\)?$")


def fields_of(files: Mapping[str, bytes]) -> dict[Field, str]:
    """Every field the report names: (table, field) -> "column" or "measure" (a queryRef alone: "column")."""
    found: dict[Field, str] = {}
    for path, data in files.items():
        if not path.endswith(".json"):
            continue
        aliases: dict[str, str] = {}

        def visit(node: dict[str, Any], aliases: dict[str, str] = aliases) -> dict[str, Any]:
            aliases.update(_aliases(node))
            ref = _ref(node, aliases)
            if ref is not None:
                kind, table, name = ref
                if found.get((table, name)) != "measure":
                    found[(table, name)] = kind
            return node

        try:
            _walk(json.loads(data.decode("utf-8-sig")), visit)
        except ValueError:
            continue
    return found


# ===== the mapping =====


@dataclass(frozen=True)
class Mapped:
    field: Field
    kind: str
    to: Field | None  # None: left as it is (Power BI shows its broken field)
    matched: bool  # found by name (ticked) rather than picked or left

    def to_json(self) -> dict[str, Any]:
        return {
            "table": self.field[0],
            "field": self.field[1],
            "kind": self.kind,
            "to": {"table": self.to[0], "field": self.to[1]} if self.to else None,
            "matched": self.matched,
        }


def propose(
    fields: Mapping[Field, str], ours: Mapping[str, Iterable[str]], measures: Iterable[Field] = ()
) -> list[Mapped]:
    """Each field matched to our model by name in any case (`ours`: table -> its columns; `measures`: the
    measures that come along, by their table and name in OUR names); the rest unmatched."""
    tables = {t.casefold(): t for t in ours}
    columns = {t: {c.casefold(): c for c in cs} for t, cs in ours.items()}
    brought = {(t.casefold(), m.casefold()): (t, m) for t, m in measures}
    out: list[Mapped] = []
    for (table, name), kind in sorted(fields.items(), key=lambda x: (x[0][0].casefold(), x[0][1].casefold())):
        ours_table = tables.get(table.casefold())
        to: Field | None = None
        if ours_table is not None:
            column = columns[ours_table].get(name.casefold())
            if column is not None:
                to = (ours_table, column)
            elif (ours_table.casefold(), name.casefold()) in brought:
                to = brought[(ours_table.casefold(), name.casefold())]
        out.append(Mapped((table, name), kind, to, to is not None))
    return out


def chosen(proposed: list[Mapped], picked: Mapping[str, Any] | None) -> list[Mapped]:
    """The mapping with the person's (or the agent's) picks: {"Table.Field": "Table.Field" | null}."""
    if not picked:
        return proposed
    out: list[Mapped] = []
    for m in proposed:
        key = f"{m.field[0]}.{m.field[1]}"
        if key not in picked:
            out.append(m)
            continue
        value = picked[key]
        if value is None or value == "":
            out.append(Mapped(m.field, m.kind, None, False))
            continue
        if not isinstance(value, str) or "." not in value:
            raise ReportError(f"{key} maps to a Table.Field name, or null to leave it.")
        table, _, name = value.partition(".")
        out.append(Mapped(m.field, m.kind, (table, name), (table, name) == m.to))
    return out


# ===== the rewrite =====


def _dax_rewrite(
    text: str, mapping: Mapping[Field, Field], tables: Mapping[str, str]
) -> tuple[str, list[str]]:
    """'Table'[Field] and Table[Field] references pointed at their new names; the unmapped ones named back."""
    missing: list[str] = []

    def one(match: re.Match[str]) -> str:
        table = match.group(1)[1:-1].replace("''", "'") if match.group(1).startswith("'") else match.group(1)
        name = match.group(2)
        to = mapping.get((table, name))
        if to is None:
            if (table, name) not in mapping and table in tables:
                missing.append(f"{table}[{name}]")
            return match.group(0)
        quoted = (
            to[0] if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", to[0]) else "'" + to[0].replace("'", "''") + "'"
        )
        return f"{quoted}[{to[1]}]"

    rewritten = re.sub(r"('(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_]*)\[([^\]]+)\]", one, text)
    return rewritten, missing


def rewrite(files: Mapping[str, bytes], mapped: Iterable[Mapped]) -> dict[str, bytes]:
    """The report's files with every reference rewritten to the chosen names (a field left: as it was)."""
    mapping = {m.field: m.to for m in mapped if m.to is not None}
    table_to: dict[str, str] = {}
    for (table, _), (to_table, _) in mapping.items():
        table_to.setdefault(table, to_table)
    out: dict[str, bytes] = {}
    for path, data in files.items():
        if not path.endswith(".json"):
            out[path] = data
            continue
        try:
            parsed = json.loads(data.decode("utf-8-sig"))
        except ValueError:
            out[path] = data
            continue
        aliases: dict[str, str] = {}

        def visit(node: dict[str, Any], aliases: dict[str, str] = aliases) -> dict[str, Any]:
            aliases.update(_aliases(node))
            node = dict(node)
            ref = _ref(node, aliases)
            if ref is not None:
                kind, table, name = ref
                to = mapping.get((table, name))
                if to is not None:
                    key = kind.capitalize()
                    inner = dict(node[key])
                    inner["Property"] = to[1]
                    expression = dict(inner.get("Expression") or {})
                    source = dict(expression.get("SourceRef") or {})
                    if "Entity" in source:
                        source["Entity"] = to[0]
                    expression["SourceRef"] = source
                    inner["Expression"] = expression
                    node[key] = inner
            if isinstance(node.get("Entity"), str) and node["Entity"] in table_to:
                node["Entity"] = table_to[node["Entity"]]
            for key in ("queryRef", "nativeQueryRef", "Name", "queryName"):
                value = node.get(key)
                if isinstance(value, str):
                    node[key] = _query_ref(value, mapping)
            if isinstance(node.get("expression"), str) and isinstance(node.get("name"), str):
                node["expression"] = _dax_rewrite(node["expression"], mapping, table_to)[0]
            if isinstance(node.get("name"), str) and isinstance(node.get("measures"), list):
                node["name"] = table_to.get(node["name"], node["name"])  # a report extension's entity
            return node

        walked = _walk(parsed, visit)
        indent = 2 if path.startswith("definition/") else None
        text = json.dumps(
            walked, ensure_ascii=False, indent=indent, separators=None if indent else (",", ":")
        )
        out[path] = (text + ("\n" if indent else "")).encode("utf-8")
    return out


def _query_ref(value: str, mapping: Mapping[Field, Field]) -> str:
    found = _QUERY_REF.match(value)
    if not found:
        return value
    to = mapping.get((found.group(1), found.group(2)))
    if to is None:
        return value
    return value.replace(f"{found.group(1)}.{found.group(2)}", f"{to[0]}.{to[1]}", 1)


@dataclass(frozen=True)
class BroughtMeasure:
    table: str
    name: str
    expression: str
    format: str = ""
    folder: str = ""


def bring_measures(
    measures: Iterable[Mapping[str, str]], mapped: Iterable[Mapped], ours: Mapping[str, Iterable[str]]
) -> tuple[list[BroughtMeasure], list[str]]:
    """The model's measures for our model: on the table their own table maps to (the mapping, else by name),
    their DAX rewritten; one naming a column we do not map is said, not written."""
    mapping = {m.field: m.to for m in mapped if m.to is not None}
    by_name = {t.casefold(): t for t in ours}
    table_to: dict[str, str] = {}
    for (table, _), (to_table, _) in mapping.items():
        table_to.setdefault(table, to_table)
    out: list[BroughtMeasure] = []
    said: list[str] = []
    every = list(measures)
    # A measure referring to another measure ([Total]) is fine; columns are checked through the mapping.
    known_tables = {m["table"] for m in every} | set(table_to)
    for m in every:
        home = table_to.get(m["table"]) or by_name.get(m["table"].casefold())
        if home is None:
            said.append(f"{m['table']}[{m['name']}]: its table {m['table']} is not in this model")
            continue
        own = {(m2["table"], m2["name"]): (home, m2["name"]) for m2 in every if m2["table"] == m["table"]}
        text, missing = _dax_rewrite(m["expression"], {**own, **mapping}, {t: t for t in known_tables})
        if missing:
            said.append(
                f"{m['table']}[{m['name']}] names {', '.join(sorted(set(missing)))}, "
                "which this model maps to nothing"
            )
            continue
        out.append(BroughtMeasure(home, m["name"], text, m.get("format", ""), m.get("folder", "")))
    return out, said
