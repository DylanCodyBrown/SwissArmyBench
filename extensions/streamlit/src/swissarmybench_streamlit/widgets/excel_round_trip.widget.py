# /// swissarmybench-widget
# format = 1
# name = "excel_round_trip"
# description = "Download rows as a workbook, fill it in, upload it back and see what changed"
# framework = "streamlit"
# group = "Forms"
# pack = "Excel"
# tags = []
# size = [8, 7]
# min_size = [4, 4]
# ///
import io

import pandas as pd
import streamlit as st
from sab_canvas import key, table

_WIDGET = "excel_round_trip"
# The rows to send out (empty: made-up sample data)
table_name = ""  # table

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
# The field that names each row (how a row coming back is matched to one sent out)
key_field = "order_id"
file_name = "fill-in.xlsx"
# The session state key the changes are handed to the page under ({"event": "save", ...})
save_event = "round_trip_saved"


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


def _save(payload):
    """The page's hand-off: {"event": "save", "widget": ..., "payload": ...} under save_event."""
    st.session_state[save_event] = {"event": "save", "widget": _WIDGET, "payload": payload}


def _plain(value):
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value.item() if hasattr(value, "item") else value


def _sample():
    return pd.DataFrame(
        {
            "order_id": [81000, 81001, 81002, 81003],
            "product": ["Desk lamp", "Kettle", "Planter", "Wok"],
            "quantity": [2, 1, 4, 3],
            "unit_price": [24.5, 39.0, 12.99, 9.5],
            "order_date": pd.to_datetime(["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04"]),
            "status": ["Delivered", "Shipped", "Pending", "Pending"],
        }
    )


openpyxl = _openpyxl()
if openpyxl is not None:
    names = [f["name"] for f in fields]
    sent = table(table_name) if table_name else _sample()
    sent = sent[[n for n in names if n in sent.columns]]
    out = _template(fields, sent, openpyxl)
    st.markdown("**1. Download, fill in in Excel**")
    st.download_button(
        "Download the workbook",
        out,
        file_name or "fill-in.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=key("download"),
    )
    st.markdown("**2. Upload it back**")
    upload = st.file_uploader("The filled workbook", type=["xlsx", "xlsm"], key=key("upload"))
    data = upload.getvalue() if upload is not None else out
    if upload is None:
        st.caption("Until one is uploaded, the download is read back as it is.")
    back, _ = _read(data, "back.xlsx", "Data", 1, "", openpyxl)
    rules = [
        {
            "column": f["name"],
            "required": f.get("required", False),
            "type": f.get("type")
            if f.get("type") in ("number", "whole", "date")
            else ("number" if f.get("type") == "money" else None),
            "choices": f.get("choices"),
        }
        for f in fields
    ]
    rules = [{k: v for k, v in r.items() if v not in (None, False)} for r in rules]
    problems = _problems(back, rules)
    before = {str(_plain(r[key_field])): r for _, r in sent.iterrows()} if key_field in sent.columns else {}
    after = {str(_plain(r[key_field])): r for _, r in back.iterrows()} if key_field in back.columns else {}
    added = [k for k in after if k not in before]
    removed = [k for k in before if k not in after]
    changed = [
        k
        for k in after
        if k in before
        and any(
            str(_plain(after[k].get(n))) != str(_plain(before[k].get(n))) for n in names if n in back.columns
        )
    ]
    st.markdown("**3. What came back**")
    first, second, third, fourth = st.columns(4)
    first.metric("Added", len(added))
    second.metric("Changed", len(changed))
    third.metric("Removed", len(removed))
    fourth.metric("Problems", len(problems))
    if problems:
        st.dataframe(pd.DataFrame(problems), hide_index=True, use_container_width=True)
    if st.button("Save the changes", key=key("save"), type="primary", disabled=bool(problems)):
        _save(
            {
                "added": [{n: _plain(after[k].get(n)) for n in names} for k in added],
                "changed": [{n: _plain(after[k].get(n)) for n in names} for k in changed],
                "removed": removed,
            }
        )
        st.success("Changes handed to the page.")
