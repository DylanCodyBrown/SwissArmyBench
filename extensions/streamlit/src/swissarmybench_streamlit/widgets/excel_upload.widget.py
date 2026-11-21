# /// swissarmybench-widget
# format = 1
# name = "excel_upload"
# description = "Upload a workbook or CSV: the sheet, header row and range; a preview and the types guessed"
# framework = "streamlit"
# group = "Inputs"
# pack = "Excel"
# tags = []
# size = [8, 6]
# min_size = [4, 3]
# ///
import io

import pandas as pd
import streamlit as st
from sab_canvas import key

label = "Upload a workbook"
# The file types taken
types = ["xlsx", "xlsm", "xls", "csv"]
# The sheet: its name, or its number from 1 (empty: the first)
sheet = ""
# The row the column names are on (within the range when there is one)
header_row: int = 1  # 1..1000
# Only these cells, e.g. A1:F200 (empty: the whole sheet)
cell_range = ""
# How many rows the preview shows
preview_rows: int = 10  # 1..1000
# The session state key the table is kept under (Map columns and Validate rows read it)
out_key = "uploaded"


def _openpyxl():
    """openpyxl, or None after saying in this widget's place how to get it."""
    try:
        import openpyxl
    except ImportError:
        st.warning("Excel files need openpyxl in this app's Python: pip install openpyxl")
        return None
    return openpyxl


def _sample_orders():
    """Made-up orders as an export might send them: headers in its own words."""
    people = ["Ada Ashdown", "Bram Brookfield", "Cleo Calloway", "Dov Dunmore", "Esme Everly"]
    products = ["Desk lamp", "Kettle", "Planter", "Wok", "Notebook"]
    return pd.DataFrame(
        [
            {
                "Order No": 81000 + at,
                "Cust. name": people[at % 5],
                "Product": products[(at * 3) % 5],
                "Qty": [2, 1, 4, 0, 3, 12, 1, 2][at % 8],
                "Unit price": [24.5, 39.0, 12.99, 9.5, 3.25][at % 5],
                "Order date": pd.Timestamp(2026, 11, 1 + at),
                "Status": ["Delivered", "Shipped", "Pending", "Delivred"][at % 4],
            }
            for at in range(12)
        ]
    )


def _read(data, file_name, sheet, header_row, cell_range, openpyxl):
    """A workbook's or a CSV's table: the sheet by its name or its number from 1 (empty: the first), the
    header on header_row (counted within cell_range when there is one, e.g. A1:F200). Returns (table,
    every sheet's name)."""
    header_row = max(1, int(header_row))
    if file_name.lower().endswith(".csv"):
        return pd.read_csv(io.BytesIO(data), skiprows=header_row - 1), []
    if file_name.lower().endswith(".xls"):
        try:
            import xlrd  # noqa: F401
        except ImportError:
            st.warning("Old .xls workbooks need xlrd in this app's Python: pip install xlrd")
            return pd.DataFrame(), []
        books = pd.read_excel(io.BytesIO(data), sheet_name=None, header=None)
        names = list(books)
        chosen = (
            names[int(sheet) - 1]
            if sheet.strip().isdigit() and 0 < int(sheet) <= len(names)
            else (sheet if sheet in books else names[0])
        )
        rows = books[chosen].values.tolist()
    else:
        book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        names = book.sheetnames
        if sheet.strip().isdigit() and 0 < int(sheet) <= len(names):
            chosen = book.worksheets[int(sheet) - 1]
        else:
            chosen = book[sheet] if sheet in names else book.worksheets[0]
        bounds = {}
        if cell_range:
            from openpyxl.utils import range_boundaries

            low_col, low_row, high_col, high_row = range_boundaries(cell_range.upper())
            bounds = {"min_col": low_col, "min_row": low_row, "max_col": high_col, "max_row": high_row}
        rows = [list(r) for r in chosen.iter_rows(values_only=True, **bounds)]
    if len(rows) < header_row:
        return pd.DataFrame(), names
    heading, seen = [], set()
    for at, cell in enumerate(rows[header_row - 1], start=1):
        name = str(cell).strip() if cell is not None and str(cell).strip() else f"column_{at}"
        while name in seen:
            name += "_2"
        seen.add(name)
        heading.append(name)
    body = [
        r + [None] * (len(heading) - len(r)) for r in rows[header_row:] if any(v not in (None, "") for v in r)
    ]
    return pd.DataFrame([r[: len(heading)] for r in body], columns=heading), names


def _guess(values):
    """A column's type in words, from its values: yes/no, whole number, decimal, date, or text."""
    filled = values.dropna()
    filled = filled[filled.astype(str).str.strip() != ""]
    if filled.empty:
        return "empty"
    words = set(filled.astype(str).str.strip().str.lower())
    if words <= {"yes", "no", "y", "n", "true", "false"}:
        return "yes/no"
    if pd.api.types.is_datetime64_any_dtype(filled) or all(hasattr(v, "year") for v in filled):
        return "date"
    numbers = pd.to_numeric(filled, errors="coerce")
    if numbers.notna().mean() >= 0.9:
        return "whole number" if (numbers.dropna() % 1 == 0).all() else "decimal"
    dates = pd.to_datetime(filled.astype(str), errors="coerce", format="mixed")
    if dates.notna().mean() >= 0.9:
        return "date"
    return "text"


def _workbook(sheets, openpyxl):
    """Tables as one formatted workbook: a sheet each, its header filled and bold, columns sized to their
    text, numbers and dates in their formats, the header frozen and filtered. Returns the file's bytes."""
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    book = openpyxl.Workbook()
    book.remove(book.active)
    for sheet_name, frame in sheets.items():
        sheet = book.create_sheet(str(sheet_name)[:31] or "Sheet")
        sheet.append([str(c) for c in frame.columns])
        for row in frame.itertuples(index=False):
            sheet.append(
                [
                    None
                    if (not isinstance(v, (list, dict)) and pd.isna(v))
                    else (v.to_pydatetime() if hasattr(v, "to_pydatetime") else v)
                    for v in row
                ]
            )
        fill = PatternFill("solid", start_color="1f4e79".lstrip("#"), end_color="1f4e79".lstrip("#"))
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="ffffff".lstrip("#"))
            cell.fill = fill
        for at, column in enumerate(frame.columns, start=1):
            letter = get_column_letter(at)
            values = frame[column]
            if pd.api.types.is_datetime64_any_dtype(values):
                style = "yyyy-mm-dd"
            elif pd.api.types.is_integer_dtype(values):
                style = "#,##0"
            elif pd.api.types.is_float_dtype(values):
                style = "#,##0.00"
            else:
                style = None
            if style:
                for cell in sheet[letter][1:]:
                    cell.number_format = style
            widest = max([len(str(column))] + [len(str(v)) for v in values.head(500)])
            sheet.column_dimensions[letter].width = min(60, widest + 2)
        if True:
            sheet.freeze_panes = "A2"
        if sheet.max_row > 1:
            sheet.auto_filter.ref = sheet.dimensions
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


openpyxl = _openpyxl()
if openpyxl is not None:
    upload = st.file_uploader(label, type=types or None, key=key("file"))
    if upload is None:
        data, file_name = (
            _workbook(
                {"Orders": _sample_orders(), "Notes": pd.DataFrame({"Note": ["Made-up sample"]})}, openpyxl
            ),
            "sample.xlsx",
        )
        st.caption("Made-up sample workbook shown until a file is uploaded.")
    else:
        data, file_name = upload.getvalue(), upload.name
    frame, names = _read(data, file_name, sheet, header_row, cell_range, openpyxl)
    if len(names) > 1:
        default = (
            names.index(sheet)
            if sheet in names
            else (int(sheet) - 1 if sheet.strip().isdigit() and 0 < int(sheet) <= len(names) else 0)
        )
        picked = st.selectbox("Sheet", names, index=default, key=key("sheet"))
        if picked != names[default]:
            frame, names = _read(data, file_name, picked, header_row, cell_range, openpyxl)
    st.session_state[out_key] = frame
    st.caption(f"{len(frame)} rows, {len(frame.columns)} columns")
    st.dataframe(frame.head(int(preview_rows)), hide_index=True, use_container_width=True)
    with st.expander("Types guessed"):
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "column": c,
                        "type": _guess(frame[c]),
                        "blanks": int(frame[c].isna().sum()),
                        "example": next((str(v) for v in frame[c] if v is not None and str(v).strip()), ""),
                    }
                    for c in frame.columns
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
