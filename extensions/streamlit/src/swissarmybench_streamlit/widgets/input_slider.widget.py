# /// swissarmybench-widget
# format = 1
# name = "input_slider"
# description = "A number on a slider"
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
label = "Discount"
# Shown beside the label as a ?
help_text = ""
default: float = 10
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The value, for the widgets on the page that read it
value: Out[float] = None
# Its starting value from another widget (not wired: default above)
default_from: In[float] = None
# Said under the input while it is required and missing, or does not fit
validation_message = "Pick a value in range."
minimum: float = 0
maximum: float = 100
step: float = 5
# How the value is shown (printf style: %d, %.1f%%, €%d)
number_format = "%d%%"


whole = all(float(v).is_integer() for v in (default, minimum, maximum, step))


def _number(v):
    return int(v) if whole else float(v)


if default_from is not None:
    default = default_from
_key = key("value")
if _key not in st.session_state:
    st.session_state[_key] = _number(default)
value = st.slider(
    marked(label, required),
    min_value=_number(minimum),
    max_value=_number(maximum),
    step=_number(step),
    format=number_format or None,
    key=_key,
    help=help_text or None,
    disabled=disabled,
)
if required and value is None:
    problem(validation_message)
