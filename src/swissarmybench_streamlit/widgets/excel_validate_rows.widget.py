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

import pandas as pd
import streamlit as st
from sab_canvas import In, Out, Table, key, sample

# The table to check: the page's excel_map_columns' mapped, wired by itself (none yet: made-up sample data)
mapped: In[Table] = None
# The rules: a column each, with required, type (text, number, whole, date), min, max, choices, pattern
rules = [
    {"column": "order_id", "required": True, "type": "whole"},
    {"column": "quantity", "required": True, "type": "whole", "min": 1, "max": 10},
    {"column": "unit_price", "type": "number", "min": 0},
    {"column": "order_date", "type": "date"},
    {"column": "status", "choices": ["Pending", "Shipped", "Delivered", "Cancelled"]},
]
file_name = "row-problems.xlsx"
# The rows that pass, for the page's widgets
valid: Out[Table] = None
all_good = "Every row passes its rules."

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


if mapped is not None and len(mapped.columns):
    frame = mapped.reset_index(drop=True)
else:
    sample = sample(kind="orders")
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
valid = frame.drop(index=[r - 1 for r in bad_rows])
first, second, third = st.columns(3)
first.metric("Rows", len(frame))
second.metric("Rows that pass", len(frame) - len(bad_rows))
third.metric("Problems", len(problems))
if not problems:
    st.success(all_good)
else:
    shown = pd.DataFrame(problems)
    st.dataframe(shown, hide_index=True, use_container_width=True)
    if _openpyxl():
        data, mime = (
            _workbook({"Problems": shown}),
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
