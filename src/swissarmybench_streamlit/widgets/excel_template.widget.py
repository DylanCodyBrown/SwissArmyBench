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


if _openpyxl():
    needed = [f["name"] for f in fields if f.get("required")]
    st.caption(f"{len(fields)} fields" + (f", required: {', '.join(needed)}" if needed else ""))
    st.download_button(
        label,
        _template(fields, None),
        file_name or "template.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=key("download"),
        type="primary",
    )
