"""A workbook's design: its rules (the Accounting extension's domain; no I/O).

workbook.design.json holds the design and no data:

    {"format": 1, "kind": "workbook", "title": "Cession statement",
     "sheets": [{"id": "s1", "name": "Summary", "freeze": "A5", "tab_colour": "#1F3864",
                 "print": {"orientation": "landscape", "paper": "A4", "fit_width": true,
                           "header": "Made-up Re", "footer": "Page &P of &N"},
                 "blocks": [{"id": "b1", "kind": "title", "cell": "A1", "w": 6, "h": 1, "text": "..."},
                            {"id": "b2", "kind": "table", "cell": "A4", "w": 5, "h": 12,
                             "source": {"table": "cessions"},
                             "columns": [{"name": "premium", "format": "currency", "total": "sum"}],
                             "total_row": true, "conditional": [{"column": "loss_ratio", "op": ">",
                             "value": 0.8, "fill": "#F8D7DA"}], "style": {"theme": "banded"}},
                            {"id": "b3", "kind": "pivot", "cell": "H4", "source": {"query": "SELECT ..."},
                             "rows": ["treaty"], "columns": ["period"],
                             "values": [{"column": "premium", "agg": "sum", "format": "currency"}]},
                            {"id": "b4", "kind": "chart", "cell": "H20", "w": 8, "h": 15,
                             "chart": "combo", "from": "b3", "category": "treaty",
                             "series": ["premium", "claims"], "line_series": ["claims"]}]}]}

A block sits at its top-left cell and covers w columns by h rows on the canvas (a chart's size in the
workbook; a table's and a pivot's real size is their data's, known once played). The rules here: a design
checked and made whole (ids given, names unique, sizes in range), its edits (sheets added, renamed,
removed; blocks placed, changed, moved between sheets, removed), the blocks that overlap, and the tables
a design reads (a query's by sqlglot).
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from typing import Any

FORMAT = 1
KINDS = ("title", "text", "table", "pivot", "chart")
CHARTS = ("bar", "column", "line", "pie", "combo")
AGGREGATES = ("sum", "count", "average", "min", "max")
OPERATORS = (">", ">=", "<", "<=", "=", "!=", "between")
TOTALS = ("sum", "count", "average", "min", "max", "")
MAX_SHEETS = 50
MAX_BLOCKS = 200
MAX_COLUMNS = 16_384
MAX_ROWS = 1_048_576
MAX_W = 60
MAX_H = 400
SIZES: dict[str, tuple[int, int]] = {
    "title": (6, 1),
    "text": (6, 3),
    "table": (5, 12),
    "pivot": (5, 10),
    "chart": (8, 15),
}
_SHEET_BAD = re.compile(r"[\[\]:*?/\\]")
_CELL = re.compile(r"^\$?([A-Za-z]{1,3})\$?(\d{1,7})$")
_COLOUR = re.compile(r"^#?[0-9A-Fa-f]{6}$")


class DesignError(ValueError):
    """A design, or an edit of one, that cannot be as asked (the message says why)."""


# ===== cells =====


def column_number(letters: str) -> int:
    n = 0
    for ch in letters.upper():
        n = n * 26 + (ord(ch) - 64)
    return n


def column_letters(n: int) -> str:
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def parse_cell(cell: Any) -> tuple[int, int]:
    """'B3' -> (row 3, column 2), within a sheet's bounds."""
    m = _CELL.match(str(cell or "").strip())
    if not m:
        raise DesignError(f"{cell!r} is not a cell: a column's letters and a row's number (B3).")
    row, column = int(m.group(2)), column_number(m.group(1))
    if not (1 <= row <= MAX_ROWS and 1 <= column <= MAX_COLUMNS):
        raise DesignError(f"{cell} is outside a sheet.")
    return row, column


def cell_at(row: int, column: int) -> str:
    return f"{column_letters(column)}{row}"


# ===== checking a design =====


def _text(value: Any, what: str, limit: int = 2000) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > limit:
        raise DesignError(f"{what} is text of at most {limit:,} characters.")
    return value


def _names(value: Any, what: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value) or len(value) > 50:
        raise DesignError(f"{what} is a list of column names.")
    return list(value)


def _colour(value: Any, what: str) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not _COLOUR.match(value):
        raise DesignError(f"{what} is a colour like #1F3864.")
    return "#" + value.lstrip("#").upper()


def _format(value: Any, what: str) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or len(value) > 100 or any(ord(c) < 32 for c in value):
        raise DesignError(f"{what} is a format's name (currency, percent, date...) or an Excel format code.")
    return value


def _source(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        if isinstance(value.get("table"), str) and value["table"].strip():
            return {"table": value["table"].strip()}
        if isinstance(value.get("query"), str) and value["query"].strip():
            if len(value["query"]) > 20_000:
                raise DesignError("A block's query is at most 20,000 characters.")
            return {"query": value["query"].strip()}
    raise DesignError('A table or a pivot reads {"table": a table\'s name} or {"query": "SELECT ..."}.')


def _style(value: Any) -> dict[str, Any]:
    if value in (None, {}):
        return {}
    if not isinstance(value, dict):
        raise DesignError("A block's style is {theme, bold, italic, size, colour, fill, header_fill, align}.")
    out: dict[str, Any] = {}
    if value.get("theme") is not None:
        if value["theme"] not in ("plain", "banded", "accounting"):
            raise DesignError("A style's theme is plain, banded or accounting.")
        out["theme"] = value["theme"]
    for key in ("bold", "italic"):
        if value.get(key) is not None:
            out[key] = bool(value[key])
    if value.get("size") is not None:
        size = value["size"]
        if isinstance(size, bool) or not isinstance(size, int | float) or not 6 <= size <= 72:
            raise DesignError("A style's size is 6 to 72 points.")
        out["size"] = size
    for key in ("colour", "fill", "header_fill", "header_colour", "band_fill"):
        found = _colour(value.get(key), f"The style's {key}")
        if found:
            out[key] = found
    if value.get("align") is not None:
        if value["align"] not in ("left", "center", "right"):
            raise DesignError("A style's align is left, center or right.")
        out["align"] = value["align"]
    return out


def _size(value: Any, default: int, top: int, what: str) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= top:
        raise DesignError(f"A block's {what} is 1 to {top} cells.")
    return value


def check_block(raw: Any, block_id: str) -> dict[str, Any]:
    """One block, whole: its kind's fields checked, the rest dropped."""
    if not isinstance(raw, dict):
        raise DesignError("A block is an object with its kind and cell.")
    kind = raw.get("kind")
    if kind not in KINDS:
        raise DesignError(f"{kind!r} is not a block: {', '.join(KINDS)}.")
    row, column = parse_cell(raw.get("cell") or "A1")
    w0, h0 = SIZES[kind]
    out: dict[str, Any] = {
        "id": block_id,
        "kind": kind,
        "cell": cell_at(row, column),
        "w": _size(raw.get("w"), w0, MAX_W, "width"),
        "h": _size(raw.get("h"), h0, MAX_H, "height"),
    }
    if raw.get("name"):
        out["name"] = _text(raw["name"], "A block's name", 80)
    style = _style(raw.get("style"))
    if style:
        out["style"] = style
    if kind in ("title", "text"):
        out["text"] = _text(raw.get("text"), "A block's text", 5000)
    elif kind == "table":
        out["source"] = _source(raw.get("source"))
        columns = raw.get("columns") or []
        if not isinstance(columns, list) or len(columns) > 200:
            raise DesignError("A table's columns is a list: {name, label, format, width, total}.")
        specs = []
        for c in columns:
            if isinstance(c, str):
                c = {"name": c}
            if not isinstance(c, dict) or not isinstance(c.get("name"), str) or not c["name"]:
                raise DesignError("Each of a table's columns has its name.")
            spec: dict[str, Any] = {"name": c["name"]}
            if c.get("label"):
                spec["label"] = _text(c["label"], "A column's label", 200)
            found = _format(c.get("format"), "A column's format")
            if found:
                spec["format"] = found
            if c.get("width") is not None:
                width = c["width"]
                if isinstance(width, bool) or not isinstance(width, int | float) or not 1 <= width <= 255:
                    raise DesignError("A column's width is 1 to 255 characters.")
                spec["width"] = width
            if c.get("total") not in (None, ""):
                if c["total"] not in TOTALS:
                    raise DesignError(f"A column's total is {', '.join(t for t in TOTALS if t)}.")
                spec["total"] = c["total"]
            specs.append(spec)
        if specs:
            out["columns"] = specs
        out["total_row"] = bool(raw.get("total_row"))
        rules = raw.get("conditional") or []
        if not isinstance(rules, list) or len(rules) > 20:
            raise DesignError("A table's conditional colours are a list of rules.")
        checked = []
        for r in rules:
            if not isinstance(r, dict) or not isinstance(r.get("column"), str):
                raise DesignError("A colour rule names its column.")
            if r.get("op", ">") not in OPERATORS:
                raise DesignError(f"A colour rule's op is one of {', '.join(OPERATORS)}.")
            rule: dict[str, Any] = {"column": r["column"], "op": r.get("op", ">"), "value": r.get("value")}
            if rule["op"] == "between":
                rule["to"] = r.get("to")
            for key in ("fill", "colour"):
                found = _colour(r.get(key), f"A colour rule's {key}")
                if found:
                    rule[key] = found
            checked.append(rule)
        if checked:
            out["conditional"] = checked
    elif kind == "pivot":
        out["source"] = _source(raw.get("source"))
        out["rows"] = _names(raw.get("rows"), "A pivot's rows")
        out["columns"] = _names(raw.get("columns"), "A pivot's columns")
        if len(out["columns"]) > 3:
            raise DesignError("A pivot has at most three column fields.")
        values = raw.get("values") or []
        if not isinstance(values, list) or not values or len(values) > 10:
            raise DesignError(
                "A pivot has 1 to 10 values: {column, agg (sum, count, average, min, max), format}."
            )
        vs = []
        for v in values:
            if not isinstance(v, dict):
                raise DesignError("A pivot's value is {column, agg, format}.")
            agg = v.get("agg") or "sum"
            if agg not in AGGREGATES:
                raise DesignError(f"A pivot's agg is {', '.join(AGGREGATES)}.")
            if agg != "count" and not isinstance(v.get("column"), str):
                raise DesignError(f"A pivot's {agg} names its column.")
            value: dict[str, Any] = {"agg": agg}
            if v.get("column"):
                value["column"] = str(v["column"])
            found = _format(v.get("format"), "A value's format")
            if found:
                value["format"] = found
            if v.get("label"):
                value["label"] = _text(v["label"], "A value's label", 200)
            vs.append(value)
        out["values"] = vs
        if set(out["rows"]) & set(out["columns"]):
            raise DesignError("A column is in the pivot's rows or its columns, not both.")
        out["totals"] = raw.get("totals", True) is not False
    elif kind == "chart":
        chart = raw.get("chart") or "column"
        if chart not in CHARTS:
            raise DesignError(f"A chart is {', '.join(CHARTS)}.")
        out["chart"] = chart
        out["from"] = _text(raw.get("from"), "A chart's from", 40)
        if raw.get("category"):
            out["category"] = _text(raw["category"], "A chart's category", 200)
        out["series"] = _names(raw.get("series"), "A chart's series")
        if chart == "combo":
            out["line_series"] = _names(raw.get("line_series"), "A combo chart's line series")
        if raw.get("title"):
            out["title"] = _text(raw["title"], "A chart's title", 200)
    return out


def check_sheet_name(name: Any, taken: list[str]) -> str:
    said = name.strip() if isinstance(name, str) else ""
    if not said or len(said) > 31 or _SHEET_BAD.search(said) or said.startswith("'"):
        raise DesignError("A sheet's name is 1 to 31 characters, without [ ] : * ? / \\.")
    if said.lower() in (t.lower() for t in taken):
        raise DesignError(f"There is a sheet {said} already.")
    return said


def _print(value: Any) -> dict[str, Any]:
    if value in (None, {}):
        return {}
    if not isinstance(value, dict):
        raise DesignError("Print setup is {orientation, paper, fit_width, header, footer}.")
    out: dict[str, Any] = {}
    if value.get("orientation") is not None:
        if value["orientation"] not in ("portrait", "landscape"):
            raise DesignError("Print orientation is portrait or landscape.")
        out["orientation"] = value["orientation"]
    if value.get("paper") is not None:
        if value["paper"] not in ("A4", "Letter"):
            raise DesignError("Print paper is A4 or Letter.")
        out["paper"] = value["paper"]
    if value.get("fit_width") is not None:
        out["fit_width"] = bool(value["fit_width"])
    for key in ("header", "footer"):
        if value.get(key):
            out[key] = _text(value[key], f"The print {key}", 250)
    return out


def check(raw: Any) -> dict[str, Any]:
    """A design made whole: every sheet and block checked, ids given where missing (s1, b1...)."""
    if not isinstance(raw, dict):
        raise DesignError("A workbook design is an object with its sheets.")
    if raw.get("kind", "workbook") != "workbook":
        raise DesignError("This is not a workbook's design.")
    if isinstance(raw.get("format"), int) and raw["format"] > FORMAT:
        raise DesignError("This design was made by a newer Swiss Army Bench: update to open it.")
    sheets = raw.get("sheets")
    if not isinstance(sheets, list) or not sheets or len(sheets) > MAX_SHEETS:
        raise DesignError(f"A workbook has 1 to {MAX_SHEETS} sheets.")
    used: set[str] = set()

    def fresh(prefix: str, wanted: Any) -> str:
        if isinstance(wanted, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,40}", wanted) and wanted not in used:
            used.add(wanted)
            return wanted
        n = 1
        while f"{prefix}{n}" in used:
            n += 1
        used.add(f"{prefix}{n}")
        return f"{prefix}{n}"

    out_sheets: list[dict[str, Any]] = []
    names: list[str] = []
    total = 0
    for s in sheets:
        if not isinstance(s, dict):
            raise DesignError("A sheet is {name, blocks}.")
        name = check_sheet_name(s.get("name") or f"Sheet{len(names) + 1}", names)
        names.append(name)
        sheet: dict[str, Any] = {"id": fresh("s", s.get("id")), "name": name}
        if s.get("freeze"):
            r, c = parse_cell(s["freeze"])
            sheet["freeze"] = cell_at(r, c)
        tab = _colour(s.get("tab_colour"), "A sheet's tab colour")
        if tab:
            sheet["tab_colour"] = tab
        printing = _print(s.get("print"))
        if printing:
            sheet["print"] = printing
        blocks = s.get("blocks") or []
        if not isinstance(blocks, list):
            raise DesignError("A sheet's blocks are a list.")
        total += len(blocks)
        if total > MAX_BLOCKS:
            raise DesignError(f"A workbook has at most {MAX_BLOCKS} blocks.")
        sheet["blocks"] = [
            check_block(b, fresh("b", b.get("id") if isinstance(b, dict) else None)) for b in blocks
        ]
        out_sheets.append(sheet)
    design = {
        "format": FORMAT,
        "kind": "workbook",
        "title": _text(raw.get("title"), "The title", 200),
        "sheets": out_sheets,
    }
    every = {b["id"]: b for s in out_sheets for b in s["blocks"]}
    for block in every.values():
        if (
            block["kind"] == "chart"
            and block["from"]
            and (block["from"] not in every or every[block["from"]]["kind"] not in ("table", "pivot"))
        ):
            raise DesignError(
                f"The chart {block['id']} shows {block['from']!r}: a table's or a pivot's block."
            )
    return design


def new_design(title: str = "", sheet: str = "Summary") -> dict[str, Any]:
    """A new workbook: one sheet with its title at A1."""
    blocks = [{"kind": "title", "cell": "A1", "text": title or "Workbook"}]
    return check({"title": title, "sheets": [{"name": sheet, "blocks": blocks}]})


# ===== edits (each answers the new design, checked) =====


def _sheet(design: Mapping[str, Any], sheet: str) -> dict[str, Any]:
    for s in design["sheets"]:
        if s["id"] == sheet or s["name"] == sheet:
            return s  # type: ignore[no-any-return]
    raise DesignError(f"The workbook has no sheet {sheet!r}.")


def _next_id(design: Mapping[str, Any], prefix: str) -> str:
    used = {s["id"] for s in design["sheets"]} | {b["id"] for s in design["sheets"] for b in s["blocks"]}
    n = 1
    while f"{prefix}{n}" in used:
        n += 1
    return f"{prefix}{n}"


def add_sheet(design: Mapping[str, Any], name: str | None = None) -> tuple[dict[str, Any], str]:
    out = copy.deepcopy(dict(design))
    taken = [s["name"] for s in out["sheets"]]
    if not name:
        n = len(taken) + 1
        while f"Sheet{n}".lower() in (t.lower() for t in taken):
            n += 1
        name = f"Sheet{n}"
    sid = _next_id(out, "s")
    out["sheets"].append({"id": sid, "name": check_sheet_name(name, taken), "blocks": []})
    return check(out), sid


def change_sheet(design: Mapping[str, Any], sheet: str, changes: Mapping[str, Any]) -> dict[str, Any]:
    """A sheet renamed, its freeze panes, tab colour or print setup changed, or moved (index)."""
    out = copy.deepcopy(dict(design))
    target = _sheet(out, sheet)
    if "name" in changes:
        target["name"] = check_sheet_name(
            changes["name"], [s["name"] for s in out["sheets"] if s is not target]
        )
    for key in ("freeze", "tab_colour", "print"):
        if key in changes:
            if changes[key] in (None, "", {}):
                target.pop(key, None)
            else:
                target[key] = changes[key]
    if "index" in changes:
        index = changes["index"]
        if isinstance(index, bool) or not isinstance(index, int):
            raise DesignError("A sheet's index is a whole number.")
        out["sheets"].remove(target)
        out["sheets"].insert(max(0, min(len(out["sheets"]), index)), target)
    return check(out)


def remove_sheet(design: Mapping[str, Any], sheet: str) -> dict[str, Any]:
    out = copy.deepcopy(dict(design))
    target = _sheet(out, sheet)
    if len(out["sheets"]) == 1:
        raise DesignError("A workbook keeps at least one sheet.")
    out["sheets"].remove(target)
    gone = {b["id"] for b in target["blocks"]}
    for s in out["sheets"]:
        for b in s["blocks"]:
            if b["kind"] == "chart" and b.get("from") in gone:
                b["from"] = ""
    return check(out)


def add_block(design: Mapping[str, Any], sheet: str, block: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    out = copy.deepcopy(dict(design))
    target = _sheet(out, sheet)
    bid = _next_id(out, "b")
    raw = dict(block) | {"id": bid}
    if raw.get("kind") in ("table", "pivot", "chart") and not raw.get("cell"):
        raw["cell"] = free_cell(target)
    target["blocks"].append(check_block(raw, bid))
    return check(out), bid


def find_block(design: Mapping[str, Any], block: str) -> tuple[dict[str, Any], dict[str, Any]]:
    for s in design["sheets"]:
        for b in s["blocks"]:
            if b["id"] == block:
                return s, b
    raise DesignError(f"The workbook has no block {block!r}.")


def change_block(design: Mapping[str, Any], block: str, changes: Mapping[str, Any]) -> dict[str, Any]:
    """A block changed: any of its fields (its cell to move it, w and h to size it), or "sheet" to
    move it to another sheet. Its kind stays."""
    out = copy.deepcopy(dict(design))
    sheet, found = find_block(out, block)
    if "kind" in changes and changes["kind"] != found["kind"]:
        raise DesignError("A block keeps its kind: add a new one instead.")
    merged = {**found, **{k: v for k, v in changes.items() if k != "sheet"}}
    for key, value in changes.items():
        if value is None and key not in ("sheet",):
            merged.pop(key, None)
    index = sheet["blocks"].index(found)
    sheet["blocks"][index] = check_block(merged, block)
    if changes.get("sheet") and changes["sheet"] not in (sheet["id"], sheet["name"]):
        moved = sheet["blocks"].pop(index)
        _sheet(out, str(changes["sheet"]))["blocks"].append(moved)
    return check(out)


def remove_block(design: Mapping[str, Any], block: str) -> dict[str, Any]:
    out = copy.deepcopy(dict(design))
    sheet, found = find_block(out, block)
    sheet["blocks"].remove(found)
    for s in out["sheets"]:
        for b in s["blocks"]:
            if b["kind"] == "chart" and b.get("from") == block:
                b["from"] = ""
    return check(out)


def free_cell(sheet: Mapping[str, Any]) -> str:
    """Where a new block goes: column A, two rows under the lowest block."""
    bottom = 0
    for b in sheet.get("blocks") or []:
        row, _ = parse_cell(b["cell"])
        bottom = max(bottom, row + int(b.get("h") or 1) - 1)
    return cell_at(bottom + 2 if bottom else 1, 1)


# ===== what a design says about itself =====


def overlaps(sheet: Mapping[str, Any]) -> list[tuple[str, str]]:
    """The pairs of blocks on a sheet whose cells cross (their canvas sizes)."""
    found: list[tuple[str, str]] = []
    blocks = list(sheet.get("blocks") or [])
    for i, a in enumerate(blocks):
        r1, c1 = parse_cell(a["cell"])
        r2, c2 = r1 + int(a["h"]) - 1, c1 + int(a["w"]) - 1
        for b in blocks[i + 1 :]:
            s1, d1 = parse_cell(b["cell"])
            s2, d2 = s1 + int(b["h"]) - 1, d1 + int(b["w"]) - 1
            if r1 <= s2 and s1 <= r2 and c1 <= d2 and d1 <= c2:
                found.append((a["id"], b["id"]))
    return found


def tables_read(design: Mapping[str, Any]) -> list[str]:
    """Every table a design reads: its blocks' tables, and the tables its queries name (sqlglot)."""
    import sqlglot
    from sqlglot import exp

    names: dict[str, None] = {}
    for s in design["sheets"]:
        for b in s["blocks"]:
            source = b.get("source") or {}
            if "table" in source:
                names[source["table"]] = None
            elif "query" in source:
                try:
                    tree = sqlglot.parse_one(source["query"], read="duckdb")
                except sqlglot.errors.ParseError:
                    continue
                ctes = {c.alias_or_name for c in tree.find_all(exp.CTE)}
                for t in tree.find_all(exp.Table):
                    if t.name and t.name not in ctes:
                        names[t.name] = None
    return list(names)
