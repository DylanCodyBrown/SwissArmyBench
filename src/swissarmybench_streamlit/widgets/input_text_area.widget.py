# /// swissarmybench-widget
# format = 1
# name = "input_text_area"
# description = "Several lines of text"
# framework = "streamlit"
# group = "Inputs"
# pack = "User inputs"
# tags = []
# size = [4, 2]
# min_size = [2, 2]
# ///
import streamlit as st
from sab_canvas import In, Out, key, marked, problem

# The words above the input
label = "Comments"
# Shown beside the label as a ?
help_text = ""
# Shown in the box while it is empty
placeholder = "Write here"
default = ""
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The value, for the widgets on the page that read it
value: Out[str] = None
# Its starting value from another widget (not wired: default above)
default_from: In[str] = None
# Said under the input while it is required and missing, or does not fit
validation_message = "Enter some text."
# The box's height in pixels
height: int = 120  # 68..800
# The most characters (0: no limit)
max_chars: int = 0  # 0..100000


if default_from is not None:
    default = default_from
_key = key("value")
if _key not in st.session_state:
    st.session_state[_key] = default
value = st.text_area(
    marked(label, required),
    key=_key,
    height=height,
    max_chars=max_chars or None,
    help=help_text or None,
    placeholder=placeholder or None,
    disabled=disabled,
)
if required and not value.strip():
    problem(validation_message)
