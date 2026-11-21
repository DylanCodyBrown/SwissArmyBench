# /// swissarmybench-widget
# format = 1
# name = "input_checkbox"
# description = "A tick box (required: it must be ticked)"
# framework = "streamlit"
# group = "Inputs"
# pack = "User inputs"
# tags = []
# size = [3, 1]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import In, Out, key, marked, problem

# The words above the input
label = "I agree to the terms"
# Shown beside the label as a ?
help_text = ""
default = False
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The value, for the widgets on the page that read it
value: Out[bool] = None
# Its starting value from another widget (not wired: default above)
default_from: In[bool] = None
# Said under the input while it is required and missing, or does not fit
validation_message = "Tick this to go on."


if default_from is not None:
    default = default_from
_key = key("value")
if _key not in st.session_state:
    st.session_state[_key] = bool(default)
value = st.checkbox(marked(label, required), key=_key, help=help_text or None, disabled=disabled)
if required and not value:
    problem(validation_message)
