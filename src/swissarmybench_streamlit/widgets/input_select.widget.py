# /// swissarmybench-widget
# format = 1
# name = "input_select"
# description = "Pick one from a list"
# framework = "streamlit"
# group = "Inputs"
# pack = "User inputs"
# tags = []
# size = [3, 1]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import In, Out, Table, choices, key, marked, problem

# The words above the input
label = "Region"
# Shown beside the label as a ?
help_text = ""
# Shown in the box while it is empty
placeholder = "Choose an option"
# The choices
options = ["North", "South", "East", "West"]
# The choice at the start (empty: none)
default = ""
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The value, for the widgets on the page that read it
value: Out[str] = None
# Its starting value from another widget (not wired: default above)
default_from: In[str] = None
# Take the choices from a table's column instead (its distinct values, sorted; not wired: options)
options_table: In[Table] = None
options_column = ""  # column of options_table
# Said under the input while it is required and missing, or does not fit
validation_message = "Choose one."
# The viewer may type a choice that is not in the list
accept_new = False


options = choices(options, options_table, options_column)
if default_from is not None:
    default = default_from
_key = key("value")
if _key not in st.session_state:
    st.session_state[_key] = default if default in options else None
value = st.selectbox(
    marked(label, required),
    options,
    key=_key,
    accept_new_options=accept_new,
    help=help_text or None,
    placeholder=placeholder or None,
    disabled=disabled,
)
if required and value is None:
    problem(validation_message)
