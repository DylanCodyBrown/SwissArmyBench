# /// swissarmybench-widget
# format = 1
# name = "de_record_form"
# description = "A form made from a table's columns, required ones marked; Save hands the record on"
# framework = "streamlit"
# group = "Forms"
# pack = "Data entry"
# tags = []
# size = [5, 6]
# min_size = [3, 3]
# ///
import datetime

import pandas as pd
import streamlit as st
from sab_canvas import key, table

_WIDGET = "de_record_form"
# The table the form is made from (empty: made-up sample data)
table_name = ""  # table
# The columns shown, in order (empty: every column)
columns = []
# The columns that must be filled in (marked with a red star)
required_columns = ["product_name", "unit_price"]
# Start from this row of the table (0: the first; -1: an empty record)
start_row: int = 0  # -1..100000
button = "Save record"
# Said under a required field left empty
validation_message = "Fill this in."
# The session state key the record is handed to the page under ({"event": "save", ...})
save_event = "record_saved"


def _sample():
    """Made-up products (the shape of products, with a category name)."""
    rows = []
    names = ["Desk lamp", "Storage box", "Cushion", "Planter", "Trowel", "Kettle", "Claw hammer", "Notebook"]
    categories = [
        "Lighting",
        "Storage",
        "Textiles",
        "Planters",
        "Garden tools",
        "Small appliances",
        "Hand tools",
        "Paper",
    ]
    for at, name in enumerate(names):
        rows.append(
            {
                "product_id": 100 + at,
                "sku": f"LG-{100 + at:06d}",
                "product_name": name,
                "category": categories[at],
                "unit_price": round(4.99 + at * 7.5, 2),
                "launched_on": datetime.date(2024, 1 + at, 10),
                "discontinued": at == 5,
            }
        )
    frame = pd.DataFrame(rows)
    frame["launched_on"] = pd.to_datetime(frame["launched_on"])
    return frame


def _save(payload):
    """The page's hand-off: {"event": "save", "widget": ..., "payload": ...} under save_event."""
    st.session_state[save_event] = {"event": "save", "widget": _WIDGET, "payload": payload}


def _plain(value):
    """A cell as a plain Python value (for the page's hand-off: JSON-ready)."""
    if value is None or (not isinstance(value, (list, dict, str)) and pd.isna(value)):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value.item() if hasattr(value, "item") else value


frame = table(table_name) if table_name else _sample()
shown = [c for c in (columns or list(frame.columns)) if c in frame.columns]
first = frame.iloc[int(start_row)] if 0 <= int(start_row) < len(frame) else None
values, missing = {}, []
with st.form(key("form")):
    for column in shown:
        needed = column in required_columns
        label = column.replace("_", " ").capitalize() + (" :red[\\*]" if needed else "")
        dtype = frame[column].dtype
        start = None if first is None else first[column]
        if pd.api.types.is_bool_dtype(dtype):
            values[column] = st.checkbox(label, bool(start) if start is not None else False, key=key(column))
        elif pd.api.types.is_integer_dtype(dtype):
            values[column] = st.number_input(
                label, value=None if start is None else int(start), step=1, key=key(column)
            )
        elif pd.api.types.is_numeric_dtype(dtype):
            values[column] = st.number_input(
                label, value=None if start is None else float(start), format="%.2f", key=key(column)
            )
        elif pd.api.types.is_datetime64_any_dtype(dtype):
            values[column] = st.date_input(
                label, None if start is None or pd.isna(start) else start.date(), key=key(column)
            )
        else:
            values[column] = st.text_input(label, "" if start is None else str(start), key=key(column))
    saved = st.form_submit_button(button)
if saved:
    missing = [c for c in shown if c in required_columns and values.get(c) in (None, "")]
    for column in missing:
        st.markdown(f":red[{column.replace('_', ' ').capitalize()}: {validation_message}]")
    if not missing:
        _save({c: _plain(v) for c, v in values.items()})
        st.success("Record handed to the page.")
