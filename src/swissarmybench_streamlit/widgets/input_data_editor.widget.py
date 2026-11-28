# /// swissarmybench-widget
# format = 1
# name = "input_data_editor"
# description = "A grid to fill in, each column typed, required and with its choices"
# framework = "streamlit"
# group = "Inputs"
# pack = "User inputs"
# tags = []
# size = [8, 4]
# min_size = [4, 3]
# ///
import pandas as pd
import streamlit as st
from sab_canvas import In, Out, Table, key, problem

# The words above the input
label = "Order lines"
# Shown beside the label as a ?
help_text = ""
# The table to edit (empty: made-up rows)
table_name: In[Table] = None
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The value, for the widgets on the page that read it
value: Out[Table] = None
# Said under the input while it is required and missing, or does not fit
validation_message = "Fill in every required cell."
# Each column: its name, type (text, number, money, date, choice, yes/no), required, and for a choice its
# choices; a number's min and max
column_config = [
    {
        "name": "product",
        "type": "choice",
        "required": True,
        "choices": ["Desk lamp", "Kettle", "Planter", "Wok"],
    },
    {"name": "quantity", "type": "number", "required": True, "min": 1, "max": 500},
    {"name": "unit_price", "type": "money"},
    {"name": "delivery", "type": "date"},
    {"name": "gift_wrap", "type": "yes/no"},
]
# Rows can be added and taken away
add_rows = True


def _sample():
    """Made-up order lines, in column_config's columns."""
    return pd.DataFrame(
        {
            "product": ["Desk lamp", "Kettle", None],
            "quantity": [2, 1, 4],
            "unit_price": [24.5, 39.0, 12.99],
            "delivery": pd.to_datetime(["2026-11-24", "2026-11-25", None]),
            "gift_wrap": [False, True, False],
        }
    )


def _column(spec):
    name = spec.get("name", "")
    shown = name.replace("_", " ").capitalize() + (" *" if spec.get("required") else "")
    kind, needed = spec.get("type", "text"), bool(spec.get("required"))
    if kind == "number":
        return st.column_config.NumberColumn(
            shown, min_value=spec.get("min"), max_value=spec.get("max"), step=1, required=needed
        )
    if kind == "money":
        return st.column_config.NumberColumn(
            shown, min_value=spec.get("min"), max_value=spec.get("max"), format="%.2f", required=needed
        )
    if kind == "date":
        return st.column_config.DateColumn(shown, required=needed)
    if kind == "choice":
        return st.column_config.SelectboxColumn(shown, options=spec.get("choices") or [], required=needed)
    if kind == "yes/no":
        return st.column_config.CheckboxColumn(shown, required=needed)
    return st.column_config.TextColumn(shown, required=needed)


_key = key("value")
frame = table_name if table_name is not None else _sample()
if label:
    st.markdown(f"**{label}**", help=help_text or None)
edited = st.data_editor(
    frame,
    column_config={
        spec["name"]: _column(spec) for spec in column_config if spec.get("name") in frame.columns
    },
    num_rows="dynamic" if add_rows else "fixed",
    disabled=disabled,
    hide_index=True,
    use_container_width=True,
    key=_key,
)
needed = [
    spec["name"] for spec in column_config if spec.get("required") and spec.get("name") in edited.columns
]
gaps = [
    (at + 1, name)
    for name in needed
    for at, value in enumerate(edited[name])
    if value is None or pd.isna(value) or str(value).strip() == ""
]
if gaps or (required and edited.empty):
    problem(validation_message + (" " + ", ".join(f"row {r}: {c}" for r, c in gaps[:10]) if gaps else ""))
value = edited
