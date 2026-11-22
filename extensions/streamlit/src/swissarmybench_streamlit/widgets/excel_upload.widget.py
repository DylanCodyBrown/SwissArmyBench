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
from sab_canvas import File, In, Out, Table, as_file, key, sample

label = "Upload a workbook"
# The file types taken
types = ["xlsx", "xlsm", "csv"]
# The sheet: its name, or its number from 1 (empty: the first)
sheet = ""
# The row the column names are on (within the range when there is one)
header_row: int = 1  # 1..1000
# Only these cells, e.g. A1:F200 (empty: the whole sheet)
cell_range = ""
# How many rows the preview shows
preview_rows: int = 10  # 1..1000
# A file another widget gave (an input_file's file, wired by itself): read instead of this widget's own upload
file: In[File] = None
# The table read, for the page's widgets (excel_map_columns reads it by itself; wire it to any table In)
uploaded: Out[Table] = None


def _openpyxl():
    """Whether this app's Python has openpyxl (said in this widget's place, with how to get it, when not)."""
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        st.warning("Excel files need openpyxl in this app's Python: pip install openpyxl")
        return False
    return True


def _read(data, file_name, sheet, header_row, cell_range):
    """A workbook's or a CSV's table, the workbook read by the adapter (adapter.py, beside the pages): the
    sheet by its name or its number from 1 (empty: the first), the header on header_row (counted within
    cell_range when there is one, e.g. A1:F200). Returns (table, every sheet's name)."""
    header_row = max(1, int(header_row))
    if file_name.lower().endswith(".csv"):
        return pd.read_csv(io.BytesIO(data), skiprows=header_row - 1), []
    import adapter

    source = adapter.Excel(data, file_name, header_row=header_row, cells=cell_range)
    try:
        names = [t.name for t in source.tables() if t.kind == "sheet"]
    except adapter.AdapterError as error:
        st.warning(str(error))
        return pd.DataFrame(), []
    if sheet.strip().isdigit() and 0 < int(sheet) <= len(names):
        chosen = names[int(sheet) - 1]
    else:
        chosen = sheet if sheet in names else names[0]
    try:
        frame = adapter.read(source, chosen)[0].read_all().to_pandas()
    except adapter.AdapterError:  # an empty sheet, or no column names on that row
        return pd.DataFrame(), names
    return frame.dropna(how="all").reset_index(drop=True), names


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


def _workbook(sheets):
    """Tables as one formatted workbook, made by sab_excel (sab_excel.py, beside the pages): a sheet each,
    its header filled and bold, numbers and dates in their formats, the header frozen and filtered. Returns
    the file's bytes."""
    import sab_excel

    return sab_excel.build(
        {str(name): frame for name, frame in sheets.items()},
        {
            "style": {"theme": "plain", "header_fill": "1F4E79", "header_colour": "FFFFFF"},
            "formats": {"integer": "#,##0", "number": "#,##0.00", "date": "yyyy-mm-dd"},
            "freeze": True,
        },
    )


if _openpyxl():
    given = as_file(file)
    if given is not None and types and not given.name.lower().endswith(tuple("." + t for t in types)):
        st.warning(f"{given.name} is not one of {', '.join(types)}: this widget reads its own upload.")
        given = None
    if given is not None:
        upload = given
        st.caption(f"{given.name}, from the page's file")
    else:
        upload = st.file_uploader(label, type=types or None, key=key("file"))
    if upload is None:
        data, file_name = (
            _workbook({"Orders": sample(kind="orders"), "Notes": pd.DataFrame({"Note": ["Made-up sample"]})}),
            "sample.xlsx",
        )
        st.caption("Made-up sample workbook shown until a file is uploaded.")
    else:
        data, file_name = upload.getvalue(), upload.name
    frame, names = _read(data, file_name, sheet, header_row, cell_range)
    if len(names) > 1:
        default = (
            names.index(sheet)
            if sheet in names
            else (int(sheet) - 1 if sheet.strip().isdigit() and 0 < int(sheet) <= len(names) else 0)
        )
        picked = st.selectbox("Sheet", names, index=default, key=key("sheet"))
        if picked != names[default]:
            frame, names = _read(data, file_name, picked, header_row, cell_range)
    uploaded = frame
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
