# /// swissarmybench-widget
# format = 1
# name = "input_feedback"
# description = "Thumbs, faces or stars"
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
label = "How was it?"
# Shown beside the label as a ?
help_text = ""
# The rating at the start, from 0 (-1: none)
default: int = -1  # -1..4
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The value, for the widgets on the page that read it
value: Out[int] = None
# Its starting value from another widget (not wired: default above)
default_from: In[int] = None
# Said under the input while it is required and missing, or does not fit
validation_message = "Give a rating."
options = "thumbs"  # choices: thumbs, faces, stars


if default_from is not None:
    default = default_from
_key = key("value")
if _key not in st.session_state:
    st.session_state[_key] = None if default < 0 else int(default)
if label:
    st.markdown(marked(label, required), help=help_text or None)
value = st.feedback(options, key=_key, disabled=disabled)
if required and value is None:
    problem(validation_message)
