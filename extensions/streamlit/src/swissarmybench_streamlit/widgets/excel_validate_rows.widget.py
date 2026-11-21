# /// swissarmybench-widget
# format = 1
# name = "excel_validate_rows"
# description = "Check each row against rules; the problems by row and cell, downloadable"
# framework = "streamlit"
# group = "Data"
# pack = "Excel"
# tags = []
# size = [8, 5]
# min_size = [4, 3]
# ///
import io

import pandas as pd
import streamlit as st
from sab_canvas import key

# The session state key the table to check is under (empty, or nothing there: made-up sample data)
in_key = "mapped"
# The rules: a column each, with required, type (text, number, whole, date), min, max, choices, pattern
rules = [
    {"column": "order_id", "required": True, "type": "whole"},
    {"column": "quantity", "required": True, "type": "whole", "min": 1, "max": 10},
    {"column": "unit_price", "type": "number", "min": 0},
    {"column": "order_date", "type": "date"},
    {"column": "status", "choices": ["Pending", "Shipped", "Delivered", "Cancelled"]},
]
file_name = "row-problems.xlsx"
# The session state key the rows that pass are kept under
out_key = "valid"
all_good = "Every row passes its rules."

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


def _problems(frame, rules):
    """Each cell that breaks a rule: its row (from 1), column, value and the problem in words. A rule:
    column, required, type (text, number, whole, date), min, max, choices, pattern."""
    import re

    found = []
    for rule in rules:
        column = rule.get("column")
        if column not in frame.columns:
            found.append({"row": None, "column": column, "value": None, "problem": "is not in the table"})
            continue
        for at, value in frame[column].items():
            empty = (
                value is None or (not isinstance(value, str) and pd.isna(value)) or str(value).strip() == ""
            )
            number = None if empty else pd.to_numeric(pd.Series([value]), errors="coerce")[0]
            said = None
            if empty:
                said = "is required" if rule.get("required") else None
            elif rule.get("type") in ("number", "whole") and pd.isna(number):
                said = "is not a number"
            elif rule.get("type") == "whole" and number % 1 != 0:
                said = "is not a whole number"
            elif (
                rule.get("type") == "date"
                and not hasattr(value, "year")
                and pd.isna(pd.to_datetime(pd.Series([str(value)]), errors="coerce", format="mixed")[0])
            ):
                said = "is not a date"
            elif rule.get("choices") and str(value) not in [str(c) for c in rule["choices"]]:
                said = "is not one of " + ", ".join(str(c) for c in rule["choices"])
            elif rule.get("pattern") and not re.fullmatch(str(rule["pattern"]), str(value)):
                said = "does not match its pattern"
            elif "min" in rule and number is not None and not pd.isna(number) and number < rule["min"]:
                said = f"is under {rule['min']}"
            elif "max" in rule and number is not None and not pd.isna(number) and number > rule["max"]:
                said = f"is over {rule['max']}"
            if said:
                found.append(
                    {
                        "row": int(at) + 1,
                        "column": column,
                        "value": "" if empty else str(value),
                        "problem": said,
                    }
                )
    return found


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


found = st.session_state.get(in_key) if in_key else None
if isinstance(found, pd.DataFrame) and len(found.columns):
    frame = found.reset_index(drop=True)
else:
    sample = _sample_orders()
    frame = sample.rename(
        columns={
            "Order No": "order_id",
            "Qty": "quantity",
            "Unit price": "unit_price",
            "Order date": "order_date",
            "Status": "status",
        }
    )
problems = _problems(frame, rules)
bad_rows = sorted({p["row"] for p in problems if p["row"] is not None})
st.session_state[out_key] = frame.drop(index=[r - 1 for r in bad_rows])
first, second, third = st.columns(3)
first.metric("Rows", len(frame))
second.metric("Rows that pass", len(frame) - len(bad_rows))
third.metric("Problems", len(problems))
if not problems:
    st.success(all_good)
else:
    shown = pd.DataFrame(problems)
    st.dataframe(shown, hide_index=True, use_container_width=True)
    openpyxl = _openpyxl()
    if openpyxl is not None:
        data, mime = (
            _workbook({"Problems": shown}, openpyxl),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        name = file_name
    else:
        data, mime, name = (
            shown.to_csv(index=False).encode("utf-8"),
            "text/csv",
            file_name.rsplit(".", 1)[0] + ".csv",
        )
    st.download_button("Download the problems", data, name, mime, key=key("download"))
