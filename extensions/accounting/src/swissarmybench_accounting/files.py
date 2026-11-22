"""The Accounting extension's driven edge: its files (the design, bind.json, templates, workbook.py), a
workbook read back for people (Play's preview, a template on the canvas), and the builder run.

  preview(source)   a built or imported workbook as the page draws it: each sheet's cells as shown
                    (numbers in their format, a total's formula worked out), merged cells, column
                    widths, bold and fills, conditional colours applied, named ranges, charts (their
                    kind, anchor, series and values). At most PREVIEW_ROWS by PREVIEW_COLUMNS a sheet
  build(design, tables)  the workbook's bytes, from sab_excel.build
"""

from __future__ import annotations

import datetime as dt
import io
import json
import re
import shutil
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter, range_boundaries

from swissarmybench import sab_excel
from swissarmybench.adapters.atomic_files import write_atomic

PREVIEW_ROWS = 200
PREVIEW_COLUMNS = 40
MAX_TEMPLATE_BYTES = 20 * 1024 * 1024
RUNTIME_FILE = Path(sab_excel.__file__)


def runtime_text() -> str:
    return RUNTIME_FILE.read_text(encoding="utf-8")


# ===== files =====


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_text(path: str | Path, text: str) -> str:
    """A file written whole (a temporary file beside it, then a replace)."""
    target = Path(path)
    write_atomic(target, text)
    return str(target)


def write_json(path: str | Path, value: Any) -> str:
    return write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def exists(path: str | Path) -> bool:
    return Path(path).exists()


def is_folder(path: str | Path) -> bool:
    return Path(path).is_dir()


def mtime(path: str | Path) -> float | None:
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return None


def copy_template(source: str | Path, target: str | Path) -> str:
    """An existing workbook copied in as a template (read first: it must open as a workbook)."""
    src = Path(source).expanduser()
    if src.suffix.lower() not in (".xlsx", ".xlsm"):
        raise sab_excel.WorkbookError(f"{src.name} is not an Excel workbook (.xlsx).")
    if not src.is_file():
        raise FileNotFoundError(f"There is no workbook at {src}.")
    if src.stat().st_size > MAX_TEMPLATE_BYTES:
        raise sab_excel.WorkbookError("A template is at most 20 MB.")
    load_workbook(src)  # it opens, or it says why
    dest = Path(target)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    return str(dest)


def templates_in(folder: str | Path) -> list[str]:
    found = Path(folder) / "templates"
    return sorted(p.stem for p in found.glob("*.xlsx")) if found.is_dir() else []


def folder_of(path: str | Path) -> str:
    return str(Path(path).resolve().parent)


def join(folder: str | Path, *parts: str) -> str:
    return str(Path(folder).joinpath(*parts))


# ===== building =====


def build(design: dict[str, Any], tables: dict[str, Any]) -> bytes:
    made: bytes = sab_excel.build(tables, design)
    return made


# ===== a workbook read back for people =====


def _hex(colour: Any) -> str | None:
    rgb = getattr(colour, "rgb", None)
    if isinstance(rgb, str) and re.fullmatch(r"[0-9A-Fa-f]{8}", rgb) and rgb != "00000000":
        return "#" + rgb[2:].upper()
    return None


def shown(value: Any, code: str) -> str:
    """A value as Excel would show it in its format, near enough for a preview."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, dt.datetime | dt.date):
        day = value if isinstance(value, dt.date) else value.date()
        lowered = code.lower()
        if "mmm yyyy" in lowered and "d" not in lowered:
            return day.strftime("%b %Y")
        if "dd mmm yyyy" in lowered:
            return day.strftime("%d %b %Y")
        return (
            day.isoformat()
            if not isinstance(value, dt.datetime) or not value.time()
            else value.isoformat(sep=" ")
        )
    if isinstance(value, int | float):
        number = float(value)
        if "%" in code:
            places = len(code.split(".")[1].split("%")[0]) if "." in code else 0
            return f"{number * 100:.{places}f}%"
        places = len(re.split(r"[;_ )\"]", code.split(".")[1])[0].rstrip("#")) if "." in code else 0
        if code in ("General", "") and isinstance(value, float) and not value.is_integer():
            return f"{number:.10g}"
        grouped = "," in code
        text = f"{abs(number):,.{places}f}" if grouped else f"{abs(number):.{places}f}"
        money = '"$"' in code or "$" in code
        if number < 0:
            return f"({'$' if money else ''}{text})" if "(" in code else f"-{'$' if money else ''}{text}"
        return f"{'$' if money else ''}{text}"
    return str(value)


_FORMULA = re.compile(
    r"^=(SUM|AVERAGE|COUNTA|COUNT|MIN|MAX)\(\$?([A-Z]{1,3})\$?(\d+):\$?([A-Z]{1,3})\$?(\d+)\)$"
)


def _worked(ws: Any, formula: str) -> Any:
    """A total's formula worked out (SUM, AVERAGE, COUNT, MIN, MAX of a range on its sheet)."""
    m = _FORMULA.match(formula.replace(" ", "").upper())
    if not m:
        return None
    fn = m.group(1)
    min_col, min_row, max_col, max_row = range_boundaries(
        f"{m.group(2)}{m.group(3)}:{m.group(4)}{m.group(5)}"
    )
    values = [
        ws.cell(row=r, column=c).value
        for r in range(min_row or 1, (max_row or 1) + 1)
        for c in range(min_col or 1, (max_col or 1) + 1)
    ]
    if fn == "COUNTA":
        return sum(v is not None for v in values)
    numbers = [float(v) for v in values if isinstance(v, int | float) and not isinstance(v, bool)]
    if fn == "COUNT":
        return len(numbers)
    if not numbers:
        return 0
    return {
        "SUM": sum(numbers),
        "AVERAGE": sum(numbers) / len(numbers),
        "MIN": min(numbers),
        "MAX": max(numbers),
    }[fn]


def _rules(ws: Any) -> list[tuple[tuple[int, int, int, int], str, list[float], str | None]]:
    out = []
    for area in ws.conditional_formatting:
        for rule in area.rules:
            if rule.type != "cellIs" or rule.dxf is None:
                continue
            fills = rule.dxf.fill
            fill = (_hex(fills.bgColor) or _hex(fills.fgColor)) if fills is not None else None
            try:
                numbers = [float(f) for f in rule.formula]
            except (TypeError, ValueError):
                continue
            for rng in str(area.sqref).split():
                min_col, min_row, max_col, max_row = range_boundaries(rng)
                out.append(
                    ((min_row or 1, min_col or 1, max_row or 1, max_col or 1), rule.operator, numbers, fill)
                )
    return out


def _hit(op: str, value: float, numbers: list[float]) -> bool:
    a = numbers[0]
    return {
        "greaterThan": value > a,
        "greaterThanOrEqual": value >= a,
        "lessThan": value < a,
        "lessThanOrEqual": value <= a,
        "equal": value == a,
        "notEqual": value != a,
        "between": len(numbers) > 1 and a <= value <= numbers[1],
    }.get(op, False)


def _series_values(book: Any, ref: Any) -> list[Any]:
    try:
        text = ref.numRef.f if getattr(ref, "numRef", None) is not None else ref.strRef.f
    except AttributeError:
        return []
    sheet, _, cells = str(text).rpartition("!")
    sheet = sheet.strip("'")
    if sheet not in book.sheetnames:
        return []
    min_col, min_row, _max_col, max_row = range_boundaries(cells.replace("$", ""))
    ws = book[sheet]
    return [ws.cell(row=r, column=min_col or 1).value for r in range(min_row or 1, (max_row or 1) + 1)][
        :PREVIEW_ROWS
    ]


def _charts(book: Any, ws: Any) -> list[dict[str, Any]]:
    out = []
    for chart in ws._charts:
        anchor = getattr(chart.anchor, "_from", None)
        kinds = [chart, *getattr(chart, "_charts", [])[1:]] if hasattr(chart, "_charts") else [chart]
        tagname = chart.tagname
        kind = {
            "barChart": "column" if getattr(chart, "type", "col") == "col" else "bar",
            "lineChart": "line",
            "pieChart": "pie",
        }.get(tagname, tagname)
        series: list[dict[str, Any]] = []
        categories: list[Any] = []
        for part in kinds:
            part_kind = {
                "barChart": kind if part is chart else "column",
                "lineChart": "line",
                "pieChart": "pie",
            }.get(part.tagname, kind)
            for s in part.series:
                name = ""
                if s.tx is not None and s.tx.strRef is not None:
                    found = _series_values(book, s.tx)
                    name = str(found[0]) if found else ""
                values = _series_values(book, s.val) if s.val is not None else []
                if s.cat is not None and not categories:
                    categories = [("" if v is None else str(v)) for v in _series_values(book, s.cat)]
                series.append(
                    {
                        "name": name,
                        "kind": part_kind,
                        "values": [v if isinstance(v, int | float) else None for v in values],
                    }
                )
        if len(kinds) > 1 or (any(s["kind"] == "line" for s in series) and kind != "line"):
            kind = "combo"
        title = None
        if chart.title is not None and chart.title.tx is not None and chart.title.tx.rich is not None:
            title = "".join(r.t for p in chart.title.tx.rich.p for r in (p.r or []))
        out.append(
            {
                "kind": kind,
                "cell": f"{get_column_letter(anchor.col + 1)}{anchor.row + 1}"
                if anchor is not None
                else "A1",
                "width": chart.width,
                "height": chart.height,
                "title": title,
                "categories": categories,
                "series": series,
            }
        )
    return out


def preview(
    source: bytes | str | Path, rows: int = PREVIEW_ROWS, columns: int = PREVIEW_COLUMNS
) -> dict[str, Any]:
    """A workbook as the page draws it (see the module's words)."""
    book = load_workbook(io.BytesIO(source) if isinstance(source, bytes) else str(source))
    names: dict[str, str] = {}
    for name, defined in book.defined_names.items():
        dest = list(defined.destinations)
        if dest:
            names[name] = f"{dest[0][0]}!{dest[0][1].replace('$', '')}"
    sheets = []
    for ws in book.worksheets:
        max_row, max_col = min(ws.max_row, rows), min(ws.max_column, columns)
        rules = _rules(ws)
        grid: list[list[dict[str, Any] | None]] = []
        for r in range(1, max_row + 1):
            line: list[dict[str, Any] | None] = []
            for c in range(1, max_col + 1):
                cell = ws.cell(row=r, column=c)
                value = cell.value
                entry: dict[str, Any] = {}
                if isinstance(value, str) and value.startswith("="):
                    worked = _worked(ws, value)
                    entry["formula"] = value
                    value = worked if worked is not None else value
                text = shown(value, cell.number_format or "General")
                if text:
                    entry["t"] = text
                if isinstance(value, int | float) and not isinstance(value, bool):
                    entry["n"] = 1
                font = cell.font
                if font is not None and font.b:
                    entry["b"] = 1
                if font is not None and font.i:
                    entry["i"] = 1
                if font is not None and font.sz and float(font.sz) >= 13:
                    entry["size"] = float(font.sz)
                colour = _hex(font.color) if font is not None and font.color is not None else None
                if colour and colour != "#000000":
                    entry["c"] = colour
                fill = (
                    _hex(cell.fill.fgColor)
                    if cell.fill is not None and cell.fill.fill_type == "solid"
                    else None
                )
                if fill:
                    entry["fill"] = fill
                if isinstance(value, int | float) and not isinstance(value, bool):
                    for (r1, c1, r2, c2), op, numbers, rule_fill in rules:
                        if r1 <= r <= r2 and c1 <= c <= c2 and rule_fill and _hit(op, float(value), numbers):
                            entry["fill"] = rule_fill
                if cell.border is not None and cell.border.top is not None and cell.border.top.style:
                    entry["top"] = 1
                if cell.border is not None and cell.border.bottom is not None and cell.border.bottom.style:
                    entry["bottom"] = 1
                line.append(entry or None)
            grid.append(line)
        widths = {}
        for c in range(1, max_col + 1):
            width = ws.column_dimensions[get_column_letter(c)].width
            if width:
                widths[get_column_letter(c)] = round(float(width), 1)
        sheets.append(
            {
                "name": ws.title,
                "rows": grid,
                "row_count": ws.max_row,
                "column_count": ws.max_column,
                "cut": ws.max_row > rows or ws.max_column > columns,
                "merged": [str(m) for m in ws.merged_cells.ranges],
                "widths": widths,
                "freeze": ws.freeze_panes,
                "charts": _charts(book, ws),
                "print": {
                    "orientation": ws.page_setup.orientation,
                    "fit_width": bool(
                        ws.sheet_properties.pageSetUpPr and ws.sheet_properties.pageSetUpPr.fitToPage
                    ),
                    "header": ws.oddHeader.center.text,
                    "footer": ws.oddFooter.center.text,
                },
            }
        )
    return {"sheets": sheets, "names": names}


def build_statements(
    template: str, data: Any, lines: Any, args: dict[str, Any], bindings: list[dict[str, Any]], dry_run: bool
) -> list[dict[str, Any]]:
    """sab_excel's build_statements, with the app's checked arguments."""
    return sab_excel.build_statements(
        template,
        data,
        lines,
        group_by=args.get("group_by") or [],
        out_folder=args["out_folder"],
        dry_run=dry_run,
        bindings=bindings,
        key=args.get("key"),
        name=args["name"],
        number=args.get("number"),
        date=args.get("date"),
        one_workbook=args.get("one_workbook", False),
        overwrite=args.get("overwrite", False),
    )


def read_register(folder: str) -> tuple[list[str], list[tuple[Any, ...]]]:
    return sab_excel.read_register(folder)


def check_place(xlsx: str, place: str) -> None:
    """A binding's place is the template's own: a named range or a cell on one of its sheets (else
    sab_excel says which is wrong)."""
    sab_excel.place_of(load_workbook(xlsx), place)
