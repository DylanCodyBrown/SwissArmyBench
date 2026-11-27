# /// swissarmybench-widget
# format = 1
# name = "input_multiselect"
# description = "Pick several from a list"
# framework = "streamlit"
# group = "Inputs"
# pack = "User inputs"
# tags = []
# size = [4, 1]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import In, Out, Table, choices, key, marked, problem

# The words above the input
label = "Regions"
# Shown beside the label as a ?
help_text = ""
# Shown in the box while it is empty
placeholder = "Choose options"
# The choices
options = ["North", "South", "East", "West"]
# The choices picked at the start
default = ["North"]
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The value, for the widgets on the page that read it
value: Out[list[str]] = None
# Its starting value from another widget (not wired: default above)
default_from: In[list[str]] = None
# Take the choices from a table's column instead (its distinct values, sorted; not wired: options)
options_table: In[Table] = None
options_column = ""  # column of options_table
# Said under the input while it is required and missing, or does not fit
validation_message = "Choose at least one."
# The most choices (0: no limit)
max_selections: int = 0  # 0..1000


options = choices(options, options_table, options_column)
if default_from is not None:
    default = default_from
_key = key("value")
if _key not in st.session_state:
    st.session_state[_key] = [d for d in default if d in options]
value = st.multiselect(
    marked(label, required),
    options,
    key=_key,
    max_selections=max_selections or None,
    help=help_text or None,
    placeholder=placeholder or None,
    disabled=disabled,
)
if required and not value:
    problem(validation_message)
