# /// swissarmybench-blade
# format = 1
# name = "Streamlit Excel download"
# kind = "snippet"
# description = "A button that downloads the rows as an Excel workbook"
# tags = ["streamlit", "interaction", "download"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<label>>"
# ///
snippet = r"""
# Excel download: a button that downloads the rows as an Excel workbook (.xlsx).
#
# Makes: nothing (it only shows)
# Reads: <<table>>
#   a table: an open one, or the rows a filter left (the workbook holds what the filters left)
#
# Streamlit functions:
#   st.download_button(label, data, file_name, mime)   a button; a click saves `data` as a file in
#                                                      the browser's downloads
#
# The workbook is written into memory (io.BytesIO), never to a file here; pandas writes it with
# openpyxl, which the page's Python needs (pip install openpyxl).
import io

import streamlit as st

_workbook = io.BytesIO()
<<table>>.to_excel(_workbook, index=False, sheet_name="<<sheet: Orders>>")
# key= gives the widget a name of its own on the page: two widgets with the same label would
# otherwise be taken for one, and Streamlit would stop with a "duplicate widget" error.
st.download_button(
    "<<label: Download as Excel>>",
    _workbook.getvalue(),
    file_name="<<file: orders.xlsx>>",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    key="<<table>>_excel",
)
"""
