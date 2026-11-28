"""Templates and their bindings: the rules (the Accounting extension's domain; no I/O).

A template is a workbook the user already has (a cession statement, an invoice: the owner, 2026-11-17:
"imported from existing workbooks", never designed from blank). Imported, it is kept as
templates/<name>.xlsx in the project with its bindings beside it, templates/<name>.bind.json:

    {"format": 1, "template": "statement.xlsx",
     "bindings": [{"kind": "value", "place": "Cedant", "value": {"column": "cedant"}},
                  {"kind": "value", "place": "Statement!F3", "value": {"number": true}},
                  {"kind": "value", "place": "StatementDate", "value": {"date": true}, "format": "keep"},
                  {"kind": "table", "place": "Statement!A12", "columns": ["period", "premium", "claims"],
                   "rows": 1, "grow": true, "formats": {"premium": "currency"}}]}

A place is a named range, "Sheet!B3" or "B3". A value is a column of the group's row, text (with
{column} names filled), the statement's number or its date; its format is the template's own unless one
is given. A table's lines start at its place and grow (rows inserted under its area, the formulas and
merged cells below moved, a total's range made longer).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

FORMAT = 1
_NAME = re.compile(r"^[A-Za-z0-9 _.-]{1,60}$")
_PLACE = re.compile(
    r"^(?:(?:'[^']{1,31}'|[^!'\[\]:*?/\\]{1,31})!)?\$?[A-Za-z]{1,3}\$?\d{1,7}$|^[A-Za-z_\\][\w.]{0,254}$"
)


class TemplateError(ValueError):
    """A template's name or a binding that cannot be as asked (the message says why)."""


def check_name(name: Any) -> str:
    said = name.strip() if isinstance(name, str) else ""
    said = said.removesuffix(".xlsx").removesuffix(".bind.json")
    if not _NAME.match(said) or said.startswith("."):
        raise TemplateError("A template's name is letters, digits, spaces, _ . - (at most 60).")
    return said


def check_place(place: Any) -> str:
    said = place.strip() if isinstance(place, str) else ""
    if not said or not _PLACE.match(said):
        raise TemplateError(f"{place!r} is not a place: a named range, a cell (B3) or Sheet!B3.")
    return said


def check_binding(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TemplateError("A binding is {kind: value or table, place, ...}.")
    kind = raw.get("kind") or "value"
    place = check_place(raw.get("place"))
    if kind == "value":
        value = raw.get("value")
        if not isinstance(value, dict):
            raise TemplateError(
                'A value binding gives {"column": ...}, {"text": ...}, {"number": true} or {"date": true}.'
            )
        if isinstance(value.get("column"), str) and value["column"]:
            picked: dict[str, Any] = {"column": value["column"]}
        elif isinstance(value.get("text"), str):
            if len(value["text"]) > 2000:
                raise TemplateError("A binding's text is at most 2,000 characters.")
            picked = {"text": value["text"]}
        elif value.get("number") is True:
            picked = {"number": True}
        elif value.get("date") is True:
            picked = {"date": True}
        else:
            raise TemplateError(
                'A value binding gives {"column": ...}, {"text": ...}, {"number": true} or {"date": true}.'
            )
        out: dict[str, Any] = {"kind": "value", "place": place, "value": picked}
        fmt = raw.get("format")
        if fmt not in (None, ""):
            if not isinstance(fmt, str) or len(fmt) > 100:
                raise TemplateError("A binding's format is keep, a format's name or an Excel format code.")
            out["format"] = fmt
        return out
    if kind == "table":
        columns = raw.get("columns") or []
        if (
            not isinstance(columns, list)
            or not all(isinstance(c, str) and c for c in columns)
            or len(columns) > 100
        ):
            raise TemplateError("A table binding's columns are the lines' column names, left to right.")
        rows = raw.get("rows", 1)
        if isinstance(rows, bool) or not isinstance(rows, int) or not 1 <= rows <= 10_000:
            raise TemplateError("A table binding's rows (its area in the template) is 1 or more.")
        out = {
            "kind": "table",
            "place": place,
            "columns": list(columns),
            "rows": rows,
            "grow": raw.get("grow", True) is not False,
        }
        formats = raw.get("formats") or {}
        if not isinstance(formats, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in formats.items()
        ):
            raise TemplateError("A table binding's formats are {column: format}.")
        if formats:
            out["formats"] = dict(formats)
        return out
    raise TemplateError(f"{kind!r} is not a binding: value or table.")


def check_bindings(raw: Any) -> dict[str, Any]:
    """A bind.json, whole."""
    if not isinstance(raw, dict):
        raise TemplateError("A template's bindings file is {template, bindings}.")
    found = raw.get("bindings") or []
    if not isinstance(found, list) or len(found) > 500:
        raise TemplateError("bindings is a list.")
    checked = [check_binding(b) for b in found]
    places = [b["place"].lower() for b in checked]
    if len(set(places)) != len(places):
        raise TemplateError("A place is bound once.")
    return {"format": FORMAT, "template": str(raw.get("template") or ""), "bindings": checked}


def bind(bindings: Mapping[str, Any], binding: Any) -> dict[str, Any]:
    """A place bound (replacing what it was bound to)."""
    new = check_binding(binding)
    kept = [b for b in bindings.get("bindings") or [] if b["place"].lower() != new["place"].lower()]
    return check_bindings({**bindings, "bindings": [*kept, new]})


def unbind(bindings: Mapping[str, Any], place: str) -> dict[str, Any]:
    kept = [b for b in bindings.get("bindings") or [] if b["place"].lower() != str(place).strip().lower()]
    if len(kept) == len(bindings.get("bindings") or []):
        raise TemplateError(f"{place} is not bound.")
    return check_bindings({**bindings, "bindings": kept})


def columns_needed(bindings: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """The data's columns the values read, and the lines' columns the tables write."""
    data = [
        b["value"]["column"]
        for b in bindings.get("bindings") or []
        if b["kind"] == "value" and "column" in b["value"]
    ]
    lines = [c for b in bindings.get("bindings") or [] if b["kind"] == "table" for c in b["columns"]]
    return list(dict.fromkeys(data)), list(dict.fromkeys(lines))


_PATTERN = re.compile(r"\{([^{}:!]+)(?:[:!][^{}]*)?\}")


def check_build(raw: Any) -> dict[str, Any]:
    """A build's request: {template, data, lines?, group_by, key?, out_folder, name, number?, date?,
    one_workbook?, overwrite?}."""
    if not isinstance(raw, dict):
        raise TemplateError("Send {template, data, group_by, out_folder, name}.")
    out: dict[str, Any] = {"template": check_name(raw.get("template"))}
    for key in ("data", "lines"):
        value = raw.get(key)
        if value in (None, "") and key == "lines":
            continue
        if not isinstance(value, str) or not value.strip():
            raise TemplateError(f"{key} is an open table's name.")
        out[key] = value.strip()
    for key in ("group_by", "key"):
        value = raw.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value) or len(value) > 10:
            raise TemplateError(f"{key} is a list of column names.")
        out[key] = list(value)
    out.setdefault("group_by", [])
    name = raw.get("name") or (
        "{" + "} {".join(out["group_by"]) + "}.xlsx" if out["group_by"] else "{number}.xlsx"
    )
    if not isinstance(name, str) or len(name) > 200 or "/" in name or "\\" in name or ".." in name:
        raise TemplateError("A file name pattern is one name, like {cedant} {period}.xlsx.")
    out["name"] = name
    number = raw.get("number")
    if number not in (None, {}):
        if (
            not isinstance(number, dict)
            or isinstance(number.get("start"), bool)
            or not isinstance(number.get("start", 1), int)
        ):
            raise TemplateError('Numbering is {"start": 1001, "pattern": "INV-{n:05d}"}.')
        out["number"] = {"start": number.get("start", 1), "pattern": str(number.get("pattern") or "{n}")}
    date = raw.get("date")
    if date not in (None, ""):
        if not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            raise TemplateError("The date is YYYY-MM-DD.")
        out["date"] = date
    out["one_workbook"] = bool(raw.get("one_workbook"))
    out["overwrite"] = bool(raw.get("overwrite"))
    if raw.get("out_folder") not in (None, ""):
        if not isinstance(raw["out_folder"], str):
            raise TemplateError("out_folder is a folder's path.")
        out["out_folder"] = raw["out_folder"]
    return out
