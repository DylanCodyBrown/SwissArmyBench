"""The workbook builder: a workbook's design built into an .xlsx from the data, and statements and invoices
built from a template. ONE generator (the owner, 2026-11-17): Play runs this file in the app, and Export
writes it into workbook.py whole, which builds the same workbook anywhere with openpyxl and duckdb (a
Function App included). Never Excel itself, never a real pivot table: a pivot is a summary DuckDB
computes, written as a formatted table.

  connect(tables)        a DuckDB of its own with the tables registered by name, then locked (no files,
                         no network): every block's query runs here, in the app and in workbook.py alike
  rows_of(con, source)   a block's rows: {"table": name} or {"query": "SELECT ..."}
  pivot_sql / pivot      a pivot's GROUP BY GROUPING SETS (rows, columns, values with sum, count, average,
                         min, max; totals by DuckDB), and its layout as a table
  build_workbook         the design (sheets, blocks: title, text, table, pivot, chart; formats, conditional
                         colours, freeze panes, print setup) into an openpyxl Workbook, saved when a path
  fill_template          a template workbook (its layout, formats, merged cells, named ranges kept) with its
                         places bound: a value (a column, text, the number, the date) or a table that grows
  build_statements       one workbook per group (or one workbook, a sheet per group), named from columns,
                         numbered, dated; dry_run first (the plan: files, rows, totals; nothing written);
                         a register of what was built (register.csv beside them)

Standard library, openpyxl and duckdb only: nothing of the app (workbook.py holds this file's text).
"""

from __future__ import annotations

import csv
import datetime as _dt
import decimal
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import absolute_coordinate, get_column_letter, quote_sheetname, range_boundaries
from openpyxl.utils.cell import column_index_from_string, coordinate_from_string

MAX_ROWS = 1_000_000  # one block's rows (a sheet holds 1,048,576)

# The number formats offered by name (any other text is an Excel format code, used as written).
FORMATS: dict[str, str] = {
    "general": "General",
    "integer": "#,##0",
    "number": "#,##0.00",
    "currency": '"$"#,##0.00;[Red]-"$"#,##0.00',
    "accounting": '_(* #,##0.00_);_(* (#,##0.00);_(* "-"??_);_(@_)',
    "percent": "0.0%",
    "date": "yyyy-mm-dd",
    "month": "mmm yyyy",
    "text": "@",
}
AGGREGATES: dict[str, str] = {"sum": "SUM", "count": "COUNT", "average": "AVG", "min": "MIN", "max": "MAX"}
OPERATORS: dict[str, str] = {
    ">": "greaterThan",
    ">=": "greaterThanOrEqual",
    "<": "lessThan",
    "<=": "lessThanOrEqual",
    "=": "equal",
    "!=": "notEqual",
    "between": "between",
}
CHARTS = ("bar", "column", "line", "pie", "combo")
HEADER_FILL = "1F3864"
BAND_FILL = "EEF2F8"
THIN = Side(style="thin", color="9AA5B8")


class WorkbookError(ValueError):
    """A design, template or build that cannot be done as asked (the message says why)."""


# ===== cells and formats =====


def split_cell(cell: str) -> tuple[int, int]:
    """'B3' -> (row 3, column 2)."""
    try:
        letters, row = coordinate_from_string(str(cell).replace("$", "").strip().upper())
        return int(row), column_index_from_string(letters)
    except Exception:  # openpyxl says it its own way
        raise WorkbookError(f"{cell!r} is not a cell (B3, AA10).") from None


def cell_name(row: int, column: int) -> str:
    return f"{get_column_letter(column)}{row}"


def excel_format(name: str | None) -> str | None:
    """A format's name (currency, percent, date...) or an Excel format code, as Excel's code."""
    if not name:
        return None
    return FORMATS.get(str(name).lower(), str(name))


def _colour(value: Any) -> str | None:
    text = str(value or "").strip().lstrip("#")
    return text.upper() if re.fullmatch(r"[0-9A-Fa-f]{6}", text) else None


def _plain(value: Any) -> Any:
    """A value as a cell takes it (openpyxl: numbers, text, dates, booleans)."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, _dt.datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, _dt.date | _dt.time):
        return value
    if hasattr(value, "item"):  # numpy's scalars
        try:
            return _plain(value.item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, float) and value != value:
        return None
    return str(value)


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


# ===== the data: a DuckDB of its own =====


def connect(tables: Mapping[str, Any]) -> Any:
    """A DuckDB of its own with each table registered under its name (a DataFrame, an Arrow table, or
    (columns, rows)), then locked: no files, no network, no settings changed."""
    import duckdb

    con = duckdb.connect(":memory:")
    for name, table in tables.items():
        if isinstance(table, tuple) and len(table) == 2:
            columns, rows = table
            import pyarrow as pa

            data = {c: [r[i] for r in rows] for i, c in enumerate(columns)}
            table = pa.table(data) if rows else pa.table({c: pa.array([], pa.string()) for c in columns})
        con.register(str(name), table)
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    return con


def _source_sql(source: Mapping[str, Any]) -> str:
    if isinstance(source.get("query"), str) and source["query"].strip():
        return str(source["query"]).strip().rstrip(";")
    if isinstance(source.get("table"), str) and source["table"].strip():
        return f"SELECT * FROM {_quote(source['table'])}"
    raise WorkbookError('A block reads {"table": a table\'s name} or {"query": "SELECT ..."}.')


def rows_of(con: Any, source: Mapping[str, Any]) -> tuple[list[str], list[tuple[Any, ...]]]:
    """A block's rows: its table, or its DuckDB query, at most MAX_ROWS."""
    try:
        result = con.execute(f"SELECT * FROM ({_source_sql(source)}) LIMIT {MAX_ROWS + 1}")
        columns = [d[0] for d in result.description]
        rows = [tuple(r) for r in result.fetchall()]
    except WorkbookError:
        raise
    except Exception as error:
        raise WorkbookError(
            f"The block's data could not be read: {str(error).splitlines()[0][:300]}"
        ) from None
    if len(rows) > MAX_ROWS:
        raise WorkbookError(f"A block holds at most {MAX_ROWS:,} rows.")
    return columns, rows


# ===== pivots: summaries DuckDB computes (the owner, 2026-11-17) =====


def _value_label(value: Mapping[str, Any]) -> str:
    if value.get("label"):
        return str(value["label"])
    agg = str(value.get("agg") or "sum").lower()
    column = value.get("column")
    return f"{agg.capitalize()} of {column}" if column else "Count"


def pivot_sql(
    source_sql: str, rows: Sequence[str], columns: Sequence[str], values: Sequence[Mapping[str, Any]]
) -> str:
    """One GROUP BY GROUPING SETS over the source: the cells, each row's total across the columns, each
    column's total down the rows, and the grand total; GROUPING() tells a total from a blank."""
    if not values:
        raise WorkbookError("A pivot needs at least one value (a column with sum, count or average).")
    fields = [*rows, *columns]
    if len(set(fields)) != len(fields):
        raise WorkbookError("A column is in the pivot's rows or columns once.")
    picks: list[str] = [_quote(f) for f in fields]
    for i, value in enumerate(values):
        agg = str(value.get("agg") or "sum").lower()
        if agg not in AGGREGATES:
            raise WorkbookError(f"{agg} is not a pivot value: sum, count, average, min or max.")
        column = value.get("column")
        inner = "*" if agg == "count" and not column else _quote(str(column or ""))
        if inner == '""':
            raise WorkbookError(f"{agg} needs a column.")
        picks.append(f"{AGGREGATES[agg]}({inner}) AS v{i}")
    picks += [f"GROUPING({_quote(f)}) AS g{i}" for i, f in enumerate(fields)]
    sets = {tuple(fields), tuple(rows), tuple(columns), ()}
    grouping = ", ".join(
        "(" + ", ".join(_quote(f) for f in s) + ")" for s in sorted(sets, key=len, reverse=True)
    )
    return f"SELECT {', '.join(picks)} FROM ({source_sql}) AS source GROUP BY GROUPING SETS ({grouping})"


def _key(value: Any) -> tuple[int, str, Any]:
    if value is None:
        return (2, "", 0)
    if isinstance(value, int | float | decimal.Decimal) and not isinstance(value, bool):
        return (0, "", float(value))
    return (1, str(value), 0)


def pivot(con: Any, block: Mapping[str, Any]) -> dict[str, Any]:
    """A pivot block's layout: its header, body rows (a row's labels, then each column key's values, then
    its total), and its total row; each column's format. Totals are DuckDB's (an average's total is the
    average of every row, not of the averages)."""
    rows = [str(r) for r in block.get("rows") or []]
    cols = [str(c) for c in block.get("columns") or []]
    values = list(block.get("values") or [])
    totals = block.get("totals", True) is not False
    sql = pivot_sql(_source_sql(block.get("source") or {}), rows, cols, values)
    try:
        result = con.execute(sql).fetchall()
    except Exception as error:
        raise WorkbookError(f"The pivot could not be computed: {str(error).splitlines()[0][:300]}") from None
    n, nv = len(rows) + len(cols), len(values)
    cells: dict[tuple[tuple[Any, ...], tuple[Any, ...]], list[Any]] = {}
    row_keys: dict[tuple[Any, ...], None] = {}
    col_keys: dict[tuple[Any, ...], None] = {}
    for record in result:
        keys, got, flags = record[:n], list(record[n : n + nv]), record[n + nv :]
        rk = tuple("\x00total" if flags[i] else keys[i] for i in range(len(rows)))
        ck = tuple("\x00total" if flags[len(rows) + i] else keys[len(rows) + i] for i in range(len(cols)))
        cells[(rk, ck)] = got
        if "\x00total" not in rk:
            row_keys[rk] = None
        if "\x00total" not in ck:
            col_keys[ck] = None
    total_r = tuple("\x00total" for _ in rows)
    total_c = tuple("\x00total" for _ in cols)
    ordered_rows = sorted(row_keys, key=lambda k: [_key(v) for v in k]) if rows else [total_r]
    ordered_cols = sorted(col_keys, key=lambda k: [_key(v) for v in k]) if cols else [total_c]
    labels = [_value_label(v) for v in values]
    header: list[str] = list(rows)
    formats: list[str | None] = [None] * len(rows)
    for ck in ordered_cols:
        for i, label in enumerate(labels):
            name = " · ".join("" if v is None else str(v) for v in ck)
            header.append((f"{name} · {label}" if nv > 1 else name) if cols else label)
            formats.append(excel_format(values[i].get("format")))
    if cols and totals:
        for i, label in enumerate(labels):
            header.append(f"Total · {label}" if nv > 1 else "Total")
            formats.append(excel_format(values[i].get("format")))

    def line(rk: tuple[Any, ...]) -> list[Any]:
        out: list[Any] = [None if v == "\x00total" else v for v in rk] if rows else []
        for ck in ordered_cols:
            out += cells.get((rk, ck), [None] * nv)
        if cols and totals:
            out += cells.get((rk, total_c), [None] * nv)
        return out

    body = [line(rk) for rk in ordered_rows] if rows else [line(total_r)]
    total_row: list[Any] | None = None
    if totals and rows:
        total_row = ["Total", *([None] * (len(rows) - 1))]
        for ck in ordered_cols:
            total_row += cells.get((total_r, ck), [None] * nv)
        if cols:
            total_row += cells.get((total_r, total_c), [None] * nv)
    return {"header": header, "rows": body, "total": total_row, "formats": formats, "labels": len(rows)}


# ===== building a workbook from its design =====


def _font(style: Mapping[str, Any], base: Font | None = None) -> Font:
    base = base or Font()
    return Font(
        name=base.name,
        bold=style.get("bold", base.bold),
        italic=style.get("italic", base.italic),
        size=style.get("size", base.size),
        color=_colour(style.get("colour")) or base.color,
    )


def _fill(colour: Any) -> PatternFill | None:
    found = _colour(colour)
    return PatternFill("solid", start_color=found, end_color=found) if found else None


def _merge(ws: Any, row: int, column: int, w: int, h: int) -> None:
    if w > 1 or h > 1:
        ws.merge_cells(start_row=row, start_column=column, end_row=row + h - 1, end_column=column + w - 1)


def _widths(
    ws: Any, column: int, header: Sequence[Any], rows: Sequence[Sequence[Any]], given: Mapping[int, Any]
) -> None:
    """Each column wide enough for its words (the first 200 rows read), or as the design says."""
    for i, name in enumerate(header):
        letter = get_column_letter(column + i)
        if isinstance(given.get(i), int | float) and given[i]:
            ws.column_dimensions[letter].width = float(given[i])
            continue
        longest = max([len(str(name))] + [len(_shown(r[i])) for r in rows[:200] if i < len(r)])
        wanted = min(50.0, max(8.0, longest * 1.15 + 2))
        if (ws.column_dimensions[letter].width or 0) < wanted:
            ws.column_dimensions[letter].width = wanted


def _shown(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    return "" if value is None else str(value)


def _write_grid(
    ws: Any,
    row: int,
    column: int,
    header: Sequence[str],
    body: Sequence[Sequence[Any]],
    formats: Sequence[str | None],
    style: Mapping[str, Any],
    total: Sequence[Any] | None = None,
    widths: Mapping[int, Any] | None = None,
) -> dict[str, Any]:
    """A header, rows and a total row at (row, column), styled; the range written, for charts."""
    theme = str(style.get("theme") or "banded")
    head_fill = _fill(style.get("header_fill") or (None if theme == "plain" else HEADER_FILL))
    head_font = Font(
        bold=True,
        color=_colour(style.get("header_colour")) or ("FFFFFF" if head_fill and theme != "plain" else None),
    )
    for i, name in enumerate(header):
        cell = ws.cell(row=row, column=column + i, value=name)
        cell.font = head_font
        if head_fill:
            cell.fill = head_fill
        cell.border = Border(bottom=THIN)
        cell.alignment = Alignment(
            horizontal="center" if i >= int(style.get("labels", 0)) else "left", wrap_text=True
        )
    band = _fill(style.get("band_fill") or BAND_FILL) if theme == "banded" else None
    for r, values in enumerate(body, start=1):
        for i, value in enumerate(values):
            cell = ws.cell(row=row + r, column=column + i, value=_plain(value))
            if i < len(formats) and formats[i]:
                cell.number_format = formats[i]
            if band and r % 2 == 0:
                cell.fill = band
    last = row + len(body)
    if total is not None:
        last += 1
        for i, value in enumerate(total):
            cell = ws.cell(
                row=last,
                column=column + i,
                value=value if isinstance(value, str) and value.startswith("=") else _plain(value),
            )
            cell.font = Font(bold=True)
            cell.border = Border(top=THIN, bottom=Side(style="double", color="9AA5B8"))
            if i < len(formats) and formats[i]:
                cell.number_format = formats[i]
    _widths(ws, column, header, body, widths or {})
    return {
        "sheet": ws.title,
        "row": row,
        "column": column,
        "header": list(header),
        "first": row + 1,
        "last": row + len(body),
        "end": last,
    }


def _table(ws: Any, con: Any, block: Mapping[str, Any]) -> dict[str, Any]:
    row, column = split_cell(block.get("cell") or "A1")
    names, rows = rows_of(con, block.get("source") or {})
    specs = [c for c in block.get("columns") or [] if isinstance(c, dict) and c.get("name")]
    if specs:
        missing = [c["name"] for c in specs if c["name"] not in names]
        if missing:
            raise WorkbookError(f"The table has no column {', '.join(missing)}. It has: {', '.join(names)}.")
        picks = [names.index(c["name"]) for c in specs]
        rows = [tuple(r[i] for i in picks) for r in rows]
        header = [str(c.get("label") or c["name"]) for c in specs]
    else:
        specs = [{"name": n} for n in names]
        header = list(names)
    formats = [excel_format(c.get("format")) for c in specs]
    total: list[Any] | None = None
    if block.get("total_row"):
        total = ["Total", *([None] * (len(specs) - 1))]
        first, last = row + 1, row + len(rows)
        for i, spec in enumerate(specs):
            how = str(spec.get("total") or "").lower()
            if i == 0 and how == "":
                continue
            if how in ("sum", "count", "average", "min", "max") and rows:
                letter = get_column_letter(column + i)
                fn = {"average": "AVERAGE", "count": "COUNTA"}.get(how, how.upper())
                total[i] = f"={fn}({letter}{first}:{letter}{last})"
    done = _write_grid(
        ws,
        row,
        column,
        header,
        rows,
        formats,
        block.get("style") or {},
        total,
        {i: c.get("width") for i, c in enumerate(specs)},
    )
    for rule in block.get("conditional") or []:
        _conditional(ws, rule, header, specs, done)
    return done


def _conditional(
    ws: Any,
    rule: Mapping[str, Any],
    header: Sequence[str],
    specs: Sequence[Mapping[str, Any]],
    done: Mapping[str, Any],
) -> None:
    names = [s["name"] for s in specs]
    if rule.get("column") not in names:
        raise WorkbookError(
            f"A colour rule names {rule.get('column')!r}: the table's columns are {', '.join(names)}."
        )
    op = str(rule.get("op") or ">")
    if op not in OPERATORS:
        raise WorkbookError(f"{op} is not a rule: {', '.join(OPERATORS)}.")
    if done["last"] < done["first"]:
        return
    letter = get_column_letter(done["column"] + names.index(rule["column"]))
    area = f"{letter}{done['first']}:{letter}{done['last']}"

    def number(v: Any) -> str:
        if isinstance(v, bool) or not isinstance(v, int | float):
            text = str(v).replace('"', '""')
            return f'"{text}"'
        return repr(v)

    formula = (
        [number(rule.get("value")), number(rule.get("to"))]
        if op == "between"
        else [number(rule.get("value"))]
    )
    fill = _fill(rule.get("fill") or "F8D7DA")
    font = Font(color=_colour(rule.get("colour"))) if _colour(rule.get("colour")) else None
    ws.conditional_formatting.add(
        area, CellIsRule(operator=OPERATORS[op], formula=formula, fill=fill, font=font)
    )


def _chart(ws: Any, block: Mapping[str, Any], written: Mapping[str, Mapping[str, Any]], book: Any) -> None:
    kind = str(block.get("chart") or "column")
    if kind not in CHARTS:
        raise WorkbookError(f"{kind} is not a chart: {', '.join(CHARTS)}.")
    source = written.get(str(block.get("from") or ""))
    if source is None:
        raise WorkbookError("A chart shows a table or a pivot on the workbook: set its from to that block.")
    header = source["header"]
    data_ws = book[source["sheet"]]
    category = block.get("category") or header[0]
    if category not in header:
        raise WorkbookError(f"The chart's category {category!r} is not a column of its table.")
    # By default every column but the category (a pivot's totals left out: a chart shows its cells).
    series = [s for s in block.get("series") or [] if s in header] or [
        h for h in header if h != category and h != "Total" and not h.startswith("Total · ")
    ][:6]
    if not series:
        raise WorkbookError("The chart has no series: pick its table's number columns.")
    lines = [s for s in block.get("line_series") or [] if s in series] if kind == "combo" else []
    first, last = source["first"], source["last"]
    if last < first:
        return
    cats = Reference(data_ws, min_col=source["column"] + header.index(category), min_row=first, max_row=last)

    def add(chart: Any, names: Sequence[str]) -> None:
        for name in names:
            col = source["column"] + header.index(name)
            chart.add_data(
                Reference(data_ws, min_col=col, min_row=source["row"], max_row=last), titles_from_data=True
            )
        chart.set_categories(cats)

    if kind == "pie":
        chart: Any = PieChart()
        add(chart, series[:1])
    elif kind == "line":
        chart = LineChart()
        add(chart, series)
    else:
        chart = BarChart()
        chart.type = "bar" if kind == "bar" else "col"
        add(chart, [s for s in series if s not in lines])
        if lines:
            line = LineChart()
            add(line, lines)
            line.y_axis.axId = 200
            line.y_axis.crosses = "max"
            chart += line
    chart.title = block.get("title") or None
    w, h = int(block.get("w") or 8), int(block.get("h") or 15)
    chart.width, chart.height = round(w * 1.69, 2), round(h * 0.53, 2)
    ws.add_chart(chart, str(block.get("cell") or "A1").upper())


def _sheet_setup(ws: Any, sheet: Mapping[str, Any]) -> None:
    if sheet.get("freeze"):
        split_cell(str(sheet["freeze"]))
        ws.freeze_panes = str(sheet["freeze"]).upper()
    if _colour(sheet.get("tab_colour")):
        ws.sheet_properties.tabColor = _colour(sheet.get("tab_colour"))
    printing = sheet.get("print") or {}
    if printing.get("orientation") in ("portrait", "landscape"):
        ws.page_setup.orientation = printing["orientation"]
    if printing.get("paper") in ("A4", "Letter"):
        ws.page_setup.paperSize = ws.PAPERSIZE_A4 if printing["paper"] == "A4" else ws.PAPERSIZE_LETTER
    if printing.get("fit_width"):
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
    if printing.get("header"):
        ws.oddHeader.center.text = str(printing["header"])
    if printing.get("footer"):
        ws.oddFooter.center.text = str(printing["footer"])


def build_workbook(
    design: Mapping[str, Any], tables: Mapping[str, Any] | Any, path: str | Path | None = None
) -> Any:
    """The design into a workbook: `tables` by name (DataFrames, Arrow tables) or a DuckDB connection
    connect() made. Saved at `path` when given. Charts come after every table and pivot, so a chart may
    show a block on another sheet."""
    con = tables if hasattr(tables, "execute") else connect(tables)
    book = Workbook()
    book.remove(book.active)
    written: dict[str, dict[str, Any]] = {}
    charts: list[tuple[Any, Mapping[str, Any]]] = []
    sheets = design.get("sheets") or []
    if not sheets:
        raise WorkbookError("The workbook has no sheet.")
    for sheet in sheets:
        ws = book.create_sheet(str(sheet.get("name") or "Sheet")[:31])
        for block in sheet.get("blocks") or []:
            kind = block.get("kind")
            try:
                if kind in ("title", "text"):
                    row, column = split_cell(block.get("cell") or "A1")
                    cell = ws.cell(row=row, column=column, value=str(block.get("text") or ""))
                    style = block.get("style") or {}
                    base = Font(bold=True, size=16) if kind == "title" else Font()
                    cell.font = _font(style, base)
                    cell.alignment = Alignment(
                        wrap_text=kind == "text", vertical="top", horizontal=style.get("align") or None
                    )
                    if _fill(style.get("fill")):
                        cell.fill = _fill(style.get("fill"))
                    _merge(
                        ws,
                        row,
                        column,
                        int(block.get("w") or 1),
                        int(block.get("h") or 1) if kind == "text" else 1,
                    )
                elif kind == "table":
                    written[str(block.get("id"))] = _table(ws, con, block)
                elif kind == "pivot":
                    row, column = split_cell(block.get("cell") or "A1")
                    shaped = pivot(con, block)
                    style = dict(block.get("style") or {}) | {"labels": shaped["labels"]}
                    written[str(block.get("id"))] = _write_grid(
                        ws,
                        row,
                        column,
                        shaped["header"],
                        shaped["rows"],
                        shaped["formats"],
                        style,
                        shaped["total"],
                    )
                elif kind == "chart":
                    charts.append((ws, block))
                else:
                    raise WorkbookError(f"{kind!r} is not a block: title, text, table, pivot or chart.")
            except WorkbookError as error:
                raise WorkbookError(f"{sheet.get('name')}, {block.get('cell')}: {error}") from None
        _sheet_setup(ws, sheet)
    for ws, block in charts:
        try:
            _chart(ws, block, written, book)
        except WorkbookError as error:
            raise WorkbookError(f"{ws.title}, {block.get('cell')}: {error}") from None
    if design.get("title"):
        book.properties.title = str(design["title"])
    if path is not None:
        book.save(str(path))
    return book


# ===== templates: an existing workbook, its places bound to data (the owner, 2026-11-17) =====


def place_of(book: Any, place: str) -> tuple[Any, int, int]:
    """A place: a named range ("InvoiceNo"), "Sheet!B3", or "B3" (the first sheet). Its sheet and cell."""
    text = str(place or "").strip()
    if not text:
        raise WorkbookError("A binding needs its place: a named range, a cell (B3) or Sheet!B3.")
    if text in book.defined_names:
        found = list(book.defined_names[text].destinations)
        if not found:
            raise WorkbookError(f"The named range {text} points nowhere.")
        sheet, ref = found[0]
        if sheet not in book.sheetnames:
            raise WorkbookError(f"The named range {text} points at the sheet {sheet}, which is not there.")
        min_col, min_row, _, _ = range_boundaries(ref.replace("$", ""))
        return book[sheet], int(min_row or 1), int(min_col or 1)
    if "!" in text:
        sheet, ref = text.rsplit("!", 1)
        sheet = sheet.strip("'")
        if sheet not in book.sheetnames:
            raise WorkbookError(f"The template has no sheet {sheet!r}. It has: {', '.join(book.sheetnames)}.")
        row, column = split_cell(ref)
        return book[sheet], row, column
    row, column = split_cell(text)
    return book.worksheets[0], row, column


_REF = re.compile(
    r"(?<![A-Za-z_\d!.])(\$?)([A-Z]{1,3})(\$?)(\d+)(?::(\$?)([A-Z]{1,3})(\$?)(\d+))?(?![\d(A-Za-z_])"
)


def _shift(formula: str, at: int, by: int, area: tuple[int, int] | None) -> str:
    """A formula with every row from `at` down moved `by` rows; a range that starts in the table's area
    and ends on its last row (`area`: its first and last) grows with it, as rows inserted inside a range
    do in Excel. References to other sheets are left as they are."""

    def moved(m: re.Match[str]) -> str:
        top = int(m.group(4))
        new_top = top + by if top >= at else top
        start = f"{m.group(1)}{m.group(2)}{m.group(3)}{new_top}"
        if m.group(6) is None:
            return start
        bottom = int(m.group(8))
        grows = area is not None and area[0] <= top <= area[1] and bottom == area[1]
        new_bottom = bottom + by if (bottom >= at or grows) else bottom
        return f"{start}:{m.group(5)}{m.group(6)}{m.group(7)}{new_bottom}"

    return _REF.sub(moved, formula)


def _grow(book: Any, ws: Any, first: int, height: int, extra: int) -> None:
    """`extra` rows inserted under a table's area (rows first..first+height-1) on `ws`: the cells, merged
    cells, formulas and named ranges below move down, the area's ranges grow, the new rows wear the area's
    last row's style."""
    if extra <= 0:
        return
    at = first + height
    merged = [r for r in ws.merged_cells.ranges]
    for r in merged:
        ws.unmerge_cells(str(r))
    ws.insert_rows(at, extra)
    for r in merged:
        min_col, min_row, max_col, max_row = r.bounds
        if min_row >= at:
            min_row, max_row = min_row + extra, max_row + extra
        ws.merge_cells(start_row=min_row, start_column=min_col, end_row=max_row, end_column=max_col)
    area = (first, at - 1)
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith("="):
                cell.value = _shift(cell.value, at, extra, area)
    for _name, defined in list(book.defined_names.items()):
        dest = list(defined.destinations)
        if len(dest) == 1 and dest[0][0] == ws.title:
            ref = dest[0][1].replace("$", "")
            min_col, min_row, max_col, max_row = range_boundaries(ref)
            if min_row is not None and min_row >= at:
                span = absolute_coordinate(
                    f"{cell_name(min_row + extra, min_col or 1)}:{cell_name((max_row or min_row) + extra, max_col or min_col or 1)}"
                )
                if span.split(":")[0] == span.split(":")[1]:
                    span = span.split(":")[0]
                sheet_ref = quote_sheetname(ws.title)
                defined.attr_text = f"{sheet_ref}!{span}"
    style_row = at - 1
    for new in range(at, at + extra):
        for col in range(1, ws.max_column + 1):
            src = ws.cell(row=style_row, column=col)
            if src.has_style:
                ws.cell(row=new, column=col)._style = src._style


def _value_for(binding: Mapping[str, Any], row: Mapping[str, Any], number: Any, date: _dt.date) -> Any:
    value = binding.get("value") or {}
    if isinstance(value, dict):
        if "column" in value:
            if value["column"] not in row:
                raise WorkbookError(f"The data has no column {value['column']!r}. It has: {', '.join(row)}.")
            return _plain(row[value["column"]])
        if "text" in value:
            text = str(value["text"])
            try:
                return text.format(
                    **{k: _shown(v) if isinstance(v, float) else v for k, v in row.items()},
                    number=number,
                    date=date.isoformat(),
                )
            except (KeyError, IndexError, ValueError):
                return text
        if value.get("number"):
            return number
        if value.get("date"):
            return date
    raise WorkbookError(
        'A value binding gives {"column": ...}, {"text": ...}, {"number": true} or {"date": true}.'
    )


def fill_template(
    template: str | Path | Any,
    bindings: Sequence[Mapping[str, Any]],
    row: Mapping[str, Any],
    lines: tuple[list[str], list[tuple[Any, ...]]] | None = None,
    number: Any = None,
    date: _dt.date | None = None,
) -> Any:
    """A copy of the template with its places filled from one group's row and its lines."""
    book = load_workbook(str(template)) if not hasattr(template, "worksheets") else template
    date = date or _dt.date.today()
    # Tables first, bottom first: a table that grows moves what is under it, values are placed after.
    tables = [b for b in bindings if b.get("kind") == "table"]
    placed = sorted(((place_of(book, str(b.get("place"))), b) for b in tables), key=lambda p: -p[0][1])
    for (ws, first, column), binding in placed:
        if lines is None:
            raise WorkbookError(
                "This template has a table: give its lines (a table joined on the group's key)."
            )
        names, rows = lines
        wanted = [str(c) for c in binding.get("columns") or names]
        missing = [c for c in wanted if c not in names]
        if missing:
            raise WorkbookError(
                f"The lines have no column {', '.join(missing)}. They have: {', '.join(names)}."
            )
        picks = [names.index(c) for c in wanted]
        height = max(1, int(binding.get("rows") or 1))
        if binding.get("grow", True) is not False:
            _grow(book, ws, first, height, len(rows) - height)
        elif len(rows) > height:
            raise WorkbookError(f"{len(rows)} lines do not fit the template's {height} rows (grow is off).")
        formats = binding.get("formats") or {}
        for r, line in enumerate(rows):
            for i, pick in enumerate(picks):
                cell = ws.cell(row=first + r, column=column + i, value=_plain(line[pick]))
                code = excel_format(formats.get(wanted[i])) if isinstance(formats, dict) else None
                if code:
                    cell.number_format = code
    for binding in bindings:
        if binding.get("kind") == "table":
            continue
        ws, r, c = place_of(book, str(binding.get("place")))
        cell = ws.cell(row=r, column=c)
        cell.value = _value_for(binding, row, number, date)
        code = excel_format(binding.get("format"))
        if code and binding.get("format") != "keep":
            cell.number_format = code
        elif isinstance(cell.value, _dt.date) and cell.number_format == "General":
            cell.number_format = FORMATS["date"]
    return book


_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def _name(pattern: str, row: Mapping[str, Any], number: Any, date: _dt.date) -> str:
    values = {k: ("" if v is None else v) for k, v in row.items()}
    try:
        text = pattern.format(**values, number=number if number is not None else "", date=date.isoformat())
    except KeyError as missing:
        raise WorkbookError(
            f"The file name names {missing}: the data's columns are {', '.join(row)}."
        ) from None
    except (IndexError, ValueError) as error:
        raise WorkbookError(f"The file name {pattern!r} cannot be filled: {error}") from None
    text = _UNSAFE.sub("-", text).strip().strip(".") or "statement"
    return text


def _numbers(spec: Mapping[str, Any] | None, count: int) -> list[Any]:
    if not spec:
        return [None] * count
    start = spec.get("start", 1)
    if isinstance(start, bool) or not isinstance(start, int):
        raise WorkbookError("The numbering starts at a whole number.")
    pattern = str(spec.get("pattern") or "{n}")
    out: list[Any] = []
    for n in range(start, start + count):
        try:
            out.append(n if pattern == "{n}" else pattern.format(n=n))
        except (KeyError, IndexError, ValueError):
            raise WorkbookError(f"The numbering {pattern!r} names only {{n}} (INV-{{n:05d}}).") from None
    return out


def _as_rows(table: Any) -> tuple[list[str], list[tuple[Any, ...]]]:
    if isinstance(table, tuple) and len(table) == 2:
        return list(table[0]), [tuple(r) for r in table[1]]
    con = connect({"t": table})
    return rows_of(con, {"table": "t"})


REGISTER = "register.csv"


def build_statements(
    template: str | Path,
    data: Any,
    lines: Any = None,
    group_by: Sequence[str] = (),
    out_folder: str | Path = ".",
    dry_run: bool = True,
    bindings: Sequence[Mapping[str, Any]] | None = None,
    key: Sequence[str] | None = None,
    name: str = "{number} {date}.xlsx",
    number: Mapping[str, Any] | None = None,
    date: str | _dt.date | None = None,
    one_workbook: bool = False,
    overwrite: bool = False,
) -> list[dict[str, Any]]:
    """One statement or invoice per group of `data` (`group_by`: its columns; a row each when empty), its
    lines the rows of `lines` whose `key` columns (default: `group_by`) match. `bindings`: the template's
    (default: <template>.bind.json beside it). Named from columns (`{cedant} {period}.xlsx`), numbered
    (`{"start": 1001, "pattern": "INV-{n:05d}"}`), dated (`date`, default today).

    dry_run (the default): the plan only, nothing written: each file, its group, its rows and totals.
    Otherwise the files are written into `out_folder` (one workbook of sheets with `one_workbook`), none
    replaced unless `overwrite`, and each is added to register.csv there. Returns the plan."""
    template = Path(template)
    if bindings is None:
        bind = template.with_name(template.stem + ".bind.json")
        if not bind.exists():
            raise WorkbookError(f"{template.name} has no bindings: {bind.name} is not beside it.")
        bindings = list(json.loads(bind.read_text(encoding="utf-8")).get("bindings") or [])
    when = (
        date if isinstance(date, _dt.date) else (_dt.date.fromisoformat(date) if date else _dt.date.today())
    )
    columns, rows = _as_rows(data)
    group_by = list(group_by)
    missing = [g for g in group_by if g not in columns]
    if missing:
        raise WorkbookError(f"The data has no column {', '.join(missing)}. It has: {', '.join(columns)}.")
    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    for record in rows:
        as_dict = dict(zip(columns, record, strict=True))
        k = tuple(as_dict[g] for g in group_by) if group_by else (len(groups),)
        groups.setdefault(k, as_dict)
    line_columns: list[str] = []
    line_rows: list[tuple[Any, ...]] = []
    keys = list(key) if key else group_by
    if lines is not None:
        line_columns, line_rows = _as_rows(lines)
        absent = [k for k in keys if k not in line_columns]
        if absent:
            raise WorkbookError(
                f"The lines have no column {', '.join(absent)} to join on. They have: {', '.join(line_columns)}."
            )
    numbers = _numbers(number, len(groups))
    out = Path(out_folder)
    plan: list[dict[str, Any]] = []
    taken: set[str] = set()
    for (_gkey, row), n in zip(groups.items(), numbers, strict=True):
        if lines is not None:
            picks = [line_columns.index(k) for k in keys]
            wanted = tuple(row[k] for k in keys)
            mine = [r for r in line_rows if tuple(r[i] for i in picks) == wanted]
        else:
            mine = []
        stem = _name(name, row, n, when)
        stem = stem[:-5] if stem.lower().endswith(".xlsx") else stem
        base, i = stem, 2
        while stem.lower() in taken:
            stem, i = f"{base} ({i})", i + 1
        taken.add(stem.lower())
        source_cols, source_rows = (
            (line_columns, mine) if lines is not None else (columns, [tuple(row[c] for c in columns)])
        )
        totals = {
            c: round(
                sum(
                    float(r[j])
                    for r in source_rows
                    if isinstance(r[j], int | float | decimal.Decimal) and not isinstance(r[j], bool)
                ),
                2,
            )
            for j, c in enumerate(source_cols)
            if c not in keys
            and any(
                isinstance(r[j], int | float | decimal.Decimal) and not isinstance(r[j], bool)
                for r in source_rows
            )
        }
        plan.append(
            {
                "file": (f"{template.stem} statements.xlsx" if one_workbook else f"{stem}.xlsx"),
                "sheet": stem[:31] if one_workbook else None,
                "group": {
                    g: _plain(row[g]) if not isinstance(row[g], _dt.date) else row[g].isoformat()
                    for g in group_by
                },
                "rows": len(mine),
                "totals": totals,
                "number": n,
                "date": when.isoformat(),
            }
        )
    if dry_run:
        return plan
    out.mkdir(parents=True, exist_ok=True)
    targets = sorted({p["file"] for p in plan})
    clashes = [t for t in targets if (out / t).exists()]
    if clashes and not overwrite:
        raise WorkbookError(
            f"These are there already: {', '.join(clashes[:5])}. Nothing was written (overwrite replaces them)."
        )
    if one_workbook:
        book = load_workbook(str(template))
        first = book.worksheets[0]
        for entry, (_gkey, row) in zip(plan, groups.items(), strict=True):
            copy = book.copy_worksheet(first)
            copy.title = entry["sheet"]
            local = [
                dict(b) | {"place": _on_sheet(book, str(b.get("place")), copy.title, first.title)}
                for b in bindings
            ]
            fill_template(
                book,
                local,
                row,
                (line_columns, _lines_for(line_columns, line_rows, keys, row)) if lines is not None else None,
                entry["number"],
                when,
            )
        book.remove(first)
        _clear_names(book, first.title)
        book.save(str(out / plan[0]["file"]))
    else:
        for entry, (_gkey, row) in zip(plan, groups.items(), strict=True):
            book = fill_template(
                template,
                bindings,
                row,
                (line_columns, _lines_for(line_columns, line_rows, keys, row)) if lines is not None else None,
                entry["number"],
                when,
            )
            book.save(str(out / entry["file"]))
    _register(out, plan)
    return plan


def _lines_for(
    columns: list[str], rows: list[tuple[Any, ...]], keys: list[str], row: Mapping[str, Any]
) -> list[tuple[Any, ...]]:
    picks = [columns.index(k) for k in keys]
    wanted = tuple(row[k] for k in keys)
    return [r for r in rows if tuple(r[i] for i in picks) == wanted]


def _on_sheet(book: Any, place: str, sheet: str, template_sheet: str) -> str:
    """A place on a copied sheet: a named range or a bare cell of the template's sheet, on the copy."""
    if place in book.defined_names:
        dest = list(book.defined_names[place].destinations)
        if dest and dest[0][0] == template_sheet:
            return f"{sheet}!{dest[0][1].replace('$', '').split(':')[0]}"
        return place
    if "!" in place:
        named, ref = place.rsplit("!", 1)
        return f"{sheet}!{ref}" if named.strip("'") == template_sheet else place
    return f"{sheet}!{place}"


def _clear_names(book: Any, sheet: str) -> None:
    for name, defined in list(book.defined_names.items()):
        if any(d[0] == sheet for d in defined.destinations):
            del book.defined_names[name]


def _register(out: Path, plan: Iterable[Mapping[str, Any]]) -> None:
    """register.csv in the folder: a line for each file built (its group, rows, totals, when)."""
    path = out / REGISTER
    fresh = not path.exists()
    built = _dt.datetime.now().isoformat(timespec="seconds")
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if fresh:
            writer.writerow(["file", "sheet", "group", "number", "date", "rows", "totals", "built"])
        for entry in plan:
            writer.writerow(
                [
                    entry["file"],
                    entry.get("sheet") or "",
                    " · ".join(str(v) for v in entry["group"].values()),
                    "" if entry.get("number") is None else entry["number"],
                    entry["date"],
                    entry["rows"],
                    json.dumps(entry["totals"], sort_keys=True),
                    built,
                ]
            )


def read_register(folder: str | Path) -> tuple[list[str], list[tuple[Any, ...]]]:
    """The register of what was built in a folder (register.csv): its header and rows."""
    path = Path(folder) / REGISTER
    if not path.exists():
        return ["file", "sheet", "group", "number", "date", "rows", "totals", "built"], []
    with path.open(newline="", encoding="utf-8") as handle:
        found = list(csv.reader(handle))
    return found[0], [tuple(r) for r in found[1:]]
