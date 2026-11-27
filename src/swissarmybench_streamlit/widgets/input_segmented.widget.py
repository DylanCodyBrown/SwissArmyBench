# /// swissarmybench-widget
# format = 1
# name = "input_segmented"
# description = "One or several choices as a segmented control"
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
label = "View"
# Shown beside the label as a ?
help_text = ""
# The choices
options = ["Day", "Week", "Month"]
# The choices picked at the start
default = ["Week"]
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
# One choice or several
selection_mode = "single"  # choices: single, multi


options = choices(options, options_table, options_column)
if default_from is not None:
    default = [default_from]
_key = key("value")
if _key not in st.session_state:
    st.session_state[_key] = (
        (default[0] if default and default[0] in options else None)
        if selection_mode == "single"
        else [d for d in default if d in options]
    )
value = st.segmented_control(
    marked(label, required),
    options,
    selection_mode=selection_mode,
    key=_key,
    help=help_text or None,
    disabled=disabled,
)
if required and not value:
    problem(validation_message)
