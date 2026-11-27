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
from sab_canvas import Event, In, Table, key

# The rows to send out (empty: made-up sample data)
table_name: In[Table] = None

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
# Fired on Save: the rows added, changed and removed; the Canvas wires what it does (call an API.py endpoint, set a page value, rerun)
saved: Event[dict] = None


def _openpyxl():
    """Whether this app's Python has openpyxl (said in this widget's place, with how to get it, when not)."""
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        st.warning("Excel files need openpyxl in this app's Python: pip install openpyxl")
        return False
    return True


def _template(fields, rows):
    """A workbook to fill in, made by sab_excel (sab_excel.py, beside the pages): a Data sheet whose header
    is the fields (required ones red), each column's type and choices checked by Excel, a note per header,
    and an Instructions sheet. `rows`: rows to start with (a table, or None). Returns the file's bytes."""
    import sab_excel

    names = [f["name"] for f in fields]
    checks = {"number": "number", "money": "number", "whole": "whole", "date": "date"}
    columns = [
        {
            "name": f["name"],
            "required": bool(f.get("required")),
            "choices": f.get("choices"),
            "check": checks.get(f.get("type", "text")),
            "note": " ".join(
                w
                for w in (
                    f.get("help", ""),
                    "Required." if f.get("required") else "",
                    f"Type: {f.get('type', 'text')}.",
                )
                if w
            ),
            "width": max(12, len(f["name"]) + 4),
        }
        for f in fields
    ]
    listed = [
        (
            f["name"],
            f.get("type", "text"),
            "yes" if f.get("required") else "",
            ", ".join(str(c) for c in f.get("choices") or []),
            f.get("help", ""),
        )
        for f in fields
    ]
    plain = {"theme": "plain", "header_fill": "1F4E79", "header_colour": "FFFFFF"}
    design = {
        "sheets": [
            {
                "name": "Data",
                "freeze": "A2",
                "blocks": [
                    {
                        "id": "data",
                        "kind": "table",
                        "cell": "A1",
                        "source": {"table": "data"},
                        "columns": columns,
                        "entry_rows": max_rows,
                        "style": plain,
                    }
                ],
            },
            {
                "name": "Instructions",
                "blocks": [
                    {
                        "id": "fields",
                        "kind": "table",
                        "cell": "A1",
                        "source": {"table": "fields"},
                        "style": plain,
                    }
                ],
            },
        ]
    }
    data = rows.reindex(columns=names) if rows is not None else (names, [])
    return sab_excel.build(
        {"data": data, "fields": (["Field", "Type", "Required", "Choices", "Help"], listed)}, design
    )


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


if _openpyxl():
    names = [f["name"] for f in fields]
    sent = table_name if table_name is not None else _sample()
    sent = sent[[n for n in names if n in sent.columns]]
    out = _template(fields, sent)
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
    back, _ = _read(data, "back.xlsx", "Data", 1, "")
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
        saved(
            {
                "added": [{n: _plain(after[k].get(n)) for n in names} for k in added],
                "changed": [{n: _plain(after[k].get(n)) for n in names} for k in changed],
                "removed": removed,
            }
        )
        st.success("Changes handed to the page.")
