# /// swissarmybench-widget
# format = 1
# name = "input_select_slider"
# description = "A choice from an ordered list on a slider"
# framework = "streamlit"
# group = "Inputs"
# pack = "User inputs"
# tags = []
# size = [4, 1]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import In, Out, key, marked, problem

# The words above the input
label = "Size"
# Shown beside the label as a ?
help_text = ""
# The choices, in order
options = ["XS", "S", "M", "L", "XL"]
default = "M"
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The value, for the widgets on the page that read it
value: Out[str] = None
# Its starting value from another widget (not wired: default above)
default_from: In[str] = None
# Said under the input while it is required and missing, or does not fit
validation_message = "Pick a value."


if default_from is not None:
    default = default_from
_key = key("value")
if _key not in st.session_state:
    st.session_state[_key] = default if default in options else options[0]
value = st.select_slider(
    marked(label, required), options, key=_key, help=help_text or None, disabled=disabled
)
if required and value is None:
    problem(validation_message)
