# /// swissarmybench-widget
# format = 1
# name = "input_number"
# description = "A number in a range: whole, decimal or money"
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
label = "Quantity"
# Shown beside the label as a ?
help_text = ""
# Shown in the box while it is empty
placeholder = "0"
# The starting value (empty box when start_empty)
default: float = 1
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The value, for the widgets on the page that read it
value: Out[float] = None
# Its starting value from another widget (not wired: default above)
default_from: In[float] = None
# Said under the input while it is required and missing, or does not fit
validation_message = "Enter a number in range."
# Start with an empty box
start_empty = False
minimum: float = 0
maximum: float = 1000
step: float = 1
# How it is shown: whole numbers, two decimals, money
number_format = "%d"  # choices: %d, %.2f, %.4f


if default_from is not None:
    default = default_from
_key = key("value")
if _key not in st.session_state:
    st.session_state[_key] = (
        None if start_empty else (int(default) if number_format == "%d" else float(default))
    )
whole = number_format == "%d"
value = st.number_input(
    marked(label, required),
    key=_key,
    min_value=int(minimum) if whole else float(minimum),
    max_value=int(maximum) if whole else float(maximum),
    step=int(step) if whole else float(step),
    format=number_format,
    help=help_text or None,
    placeholder=placeholder or None,
    disabled=disabled,
)
if required and value is None:
    problem(validation_message)
