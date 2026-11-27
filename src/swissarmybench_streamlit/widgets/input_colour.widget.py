# /// swissarmybench-widget
# format = 1
# name = "input_colour"
# description = "A colour picker"
# framework = "streamlit"
# group = "Inputs"
# pack = "User inputs"
# tags = []
# size = [2, 1]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import In, Out, key, marked, problem

# The words above the input
label = "Colour"
# Shown beside the label as a ?
help_text = ""
default = "#1f77b4"
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The value, for the widgets on the page that read it
value: Out[str] = None
# Its starting value from another widget (not wired: default above)
default_from: In[str] = None
# Said under the input while it is required and missing, or does not fit
validation_message = "Pick a colour."


if default_from is not None:
    default = default_from
_key = key("value")
if _key not in st.session_state:
    st.session_state[_key] = default
value = st.color_picker(marked(label, required), key=_key, help=help_text or None, disabled=disabled)
if required and not value:
    problem(validation_message)
