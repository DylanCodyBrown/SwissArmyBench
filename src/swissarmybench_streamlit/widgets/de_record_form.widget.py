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
import pandas as pd
import streamlit as st
from sab_canvas import Event, In, Table, key, sample

# The table the form is made from (empty: made-up sample data)
table_name: In[Table] = None
# The columns shown, in order (empty: every column)
columns = []
# The columns that must be filled in (marked with a red star)
required_columns = ["product_name", "unit_price"]
# Start from this row of the table (0: the first; -1: an empty record)
start_row: int = 0  # -1..100000
button = "Save record"
# Said under a required field left empty
validation_message = "Fill this in."
# Fired on Save: the record, a field each; the Canvas wires what it does (call an API.py endpoint, set a page value, rerun)
saved: Event[dict] = None


def _plain(value):
    """A cell as a plain Python value (for the page's hand-off: JSON-ready)."""
    if value is None or (not isinstance(value, (list, dict, str)) and pd.isna(value)):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value.item() if hasattr(value, "item") else value


frame = table_name if table_name is not None else sample(kind="products")
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
        saved({c: _plain(v) for c, v in values.items()})
        st.success("Record handed to the page.")
