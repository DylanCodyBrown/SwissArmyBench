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
    """Whether this app's Python has openpyxl (said in this widget's place, with how to get it, when not)."""
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        st.warning("Excel files need openpyxl in this app's Python: pip install openpyxl")
        return False
    return True


def _workbook(sheets):
    """Tables as one formatted workbook, made by sab_excel (sab_excel.py, beside the pages): a sheet each,
    its header filled and bold, numbers and dates in their formats, the header frozen and filtered. Returns
    the file's bytes."""
    import sab_excel

    return sab_excel.build(
        {str(name): frame for name, frame in sheets.items()},
        {
            "style": {"theme": "plain", "header_fill": header_colour, "header_colour": header_text_colour},
            "formats": {"integer": "#,##0", "number": number_format, "date": date_format},
            "freeze": freeze_header,
        },
    )


if _openpyxl():
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
        _workbook(sheets),
        file_name or "tables.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=key("download"),
        type="primary",
    )
