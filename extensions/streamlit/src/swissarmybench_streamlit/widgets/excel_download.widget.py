# /// swissarmybench-widget
# format = 1
# name = "excel_download"
# description = "Tables as a formatted workbook, a sheet each"
# framework = "streamlit"
# group = "Buttons"
# pack = "Excel"
# tags = []
# size = [4, 1]
# min_size = [2, 1]
# ///
import io

import pandas as pd
import streamlit as st
from sab_canvas import In, Table, key, sample

label = "Download as Excel"
# The tables, a sheet each, in order (not wired: made-up sample data)
tables: In[list[Table]] = None
# Each sheet's name, in the tables' order (missing ones: Sheet 1, Sheet 2, ...)
sheet_names = []
file_name = "tables.xlsx"

# How the workbook looks
header_colour = "#1f4e79"
header_text_colour = "#ffffff"
number_format = "#,##0.00"
date_format = "yyyy-mm-dd"
freeze_header = True


def _openpyxl():
    """openpyxl, or None after saying in this widget's place how to get it."""
    try:
        import openpyxl
    except ImportError:
        st.warning("Excel files need openpyxl in this app's Python: pip install openpyxl")
        return None
    return openpyxl


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
        fill = PatternFill(
            "solid", start_color=header_colour.lstrip("#"), end_color=header_colour.lstrip("#")
        )
        for cell in sheet[1]:
            cell.font = Font(bold=True, color=header_text_colour.lstrip("#"))
            cell.fill = fill
        for at, column in enumerate(frame.columns, start=1):
            letter = get_column_letter(at)
            values = frame[column]
            if pd.api.types.is_datetime64_any_dtype(values):
                style = date_format
            elif pd.api.types.is_integer_dtype(values):
                style = "#,##0"
            elif pd.api.types.is_float_dtype(values):
                style = number_format
            else:
                style = None
            if style:
                for cell in sheet[letter][1:]:
                    cell.number_format = style
            widest = max([len(str(column))] + [len(str(v)) for v in values.head(500)])
            sheet.column_dimensions[letter].width = min(60, widest + 2)
        if freeze_header:
            sheet.freeze_panes = "A2"
        if sheet.max_row > 1:
            sheet.auto_filter.ref = sheet.dimensions
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


openpyxl = _openpyxl()
if openpyxl is not None:
    if tables:
        sheets = {
            (sheet_names[at] if at < len(sheet_names) and sheet_names[at] else f"Sheet {at + 1}"): frame
            for at, frame in enumerate(tables)
        }
    else:
        orders = sample(kind="orders")
        sheets = {"Orders": orders, "Totals": orders.groupby("Product", as_index=False)["Qty"].sum()}
    st.caption(" · ".join(f"{name}: {len(frame)} rows" for name, frame in sheets.items()))
    st.download_button(
        label,
        _workbook(sheets, openpyxl),
        file_name or "tables.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=key("download"),
        type="primary",
    )
