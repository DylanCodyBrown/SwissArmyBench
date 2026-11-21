# /// swissarmybench-widget
# format = 1
# name = "excel_template"
# description = "A workbook to fill in for a set of fields, its checks built in"
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
from sab_canvas import key

label = "Download the template"

# The fields: name, type (text, number, whole, money, date), required, choices, help
fields = [
    {"name": "order_id", "type": "whole", "required": True, "help": "The order's number"},
    {
        "name": "product",
        "type": "text",
        "required": True,
        "choices": ["Desk lamp", "Kettle", "Planter", "Wok", "Notebook"],
    },
    {"name": "quantity", "type": "whole", "required": True, "help": "1 to 10"},
    {"name": "unit_price", "type": "money"},
    {"name": "order_date", "type": "date"},
    {"name": "status", "type": "text", "choices": ["Pending", "Shipped", "Delivered", "Cancelled"]},
]
# How many rows each column's checks cover
max_rows: int = 1000  # 1..100000
file_name = "template.xlsx"


def _openpyxl():
    """openpyxl, or None after saying in this widget's place how to get it."""
    try:
        import openpyxl
    except ImportError:
        st.warning("Excel files need openpyxl in this app's Python: pip install openpyxl")
        return None
    return openpyxl


def _template(fields, rows, openpyxl):
    """A workbook to fill in: a Data sheet whose header is the fields (required ones red), each column's
    type and choices checked by Excel, a note per header, and an Instructions sheet. `rows`: rows to start
    with (a table, or None). Returns the file's bytes."""
    from openpyxl.comments import Comment
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Data"
    sheet.append([f["name"] for f in fields])
    if rows is not None:
        for row in rows.itertuples(index=False):
            sheet.append(
                [
                    None if pd.isna(v) else (v.to_pydatetime() if hasattr(v, "to_pydatetime") else v)
                    for v in row
                ]
            )
    for at, field in enumerate(fields, start=1):
        letter = get_column_letter(at)
        cell = sheet.cell(row=1, column=at)
        needed = bool(field.get("required"))
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(
            "solid", start_color="C00000" if needed else "1F4E79", end_color="C00000" if needed else "1F4E79"
        )
        words = [field.get("help", ""), "Required." if needed else "", f"Type: {field.get('type', 'text')}."]
        cell.comment = Comment(" ".join(w for w in words if w), "Swiss Army Bench")
        sheet.column_dimensions[letter].width = max(12, len(field["name"]) + 4)
        area = f"{letter}2:{letter}{max_rows + 1}"
        kind = field.get("type", "text")
        rule = None
        if field.get("choices"):
            rule = DataValidation(
                type="list",
                formula1='"' + ",".join(str(c) for c in field["choices"]) + '"',
                allow_blank=not needed,
            )
        elif kind in ("number", "money"):
            rule = DataValidation(
                type="decimal", operator="greaterThanOrEqual", formula1="-1E+300", allow_blank=not needed
            )
        elif kind == "whole":
            rule = DataValidation(
                type="whole", operator="greaterThanOrEqual", formula1="-2147483647", allow_blank=not needed
            )
        elif kind == "date":
            rule = DataValidation(type="date", operator="greaterThan", formula1="1", allow_blank=not needed)
            for row in sheet[area]:
                row[0].number_format = "yyyy-mm-dd"
        if rule is not None:
            rule.error = f"{field['name']}: {field.get('help') or 'see Instructions'}"
            rule.showErrorMessage = True
            sheet.add_data_validation(rule)
            rule.add(area)
    sheet.freeze_panes = "A2"
    notes = book.create_sheet("Instructions")
    notes.append(["Field", "Type", "Required", "Choices", "Help"])
    for field in fields:
        notes.append(
            [
                field["name"],
                field.get("type", "text"),
                "yes" if field.get("required") else "",
                ", ".join(str(c) for c in field.get("choices") or []),
                field.get("help", ""),
            ]
        )
    for cell in notes[1]:
        cell.font = Font(bold=True)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


openpyxl = _openpyxl()
if openpyxl is not None:
    needed = [f["name"] for f in fields if f.get("required")]
    st.caption(f"{len(fields)} fields" + (f", required: {', '.join(needed)}" if needed else ""))
    st.download_button(
        label,
        _template(fields, None, openpyxl),
        file_name or "template.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=key("download"),
        type="primary",
    )
