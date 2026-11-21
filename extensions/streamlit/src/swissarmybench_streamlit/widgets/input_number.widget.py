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
from sab_canvas import key

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
# The session state key the value is kept under (empty: this widget's own)
state_key = ""
# Said under the input while it is required and missing, or does not fit
validation_message = "Enter a number in range."
# Start with an empty box
start_empty = False
minimum: float = 0
maximum: float = 1000
step: float = 1
# How it is shown: whole numbers, two decimals, money
number_format = "%d"  # choices: %d, %.2f, %.4f


def _label(text, needed):
    """The pack's one required marker: a red star after the label."""
    return f"{text} :red[\\*]" if needed else text


def _problem(message):
    """The pack's one error look, under the input."""
    st.markdown(f":red[{message}]")


_key = state_key or key("value")
if _key not in st.session_state:
    st.session_state[_key] = (
        None if start_empty else (int(default) if number_format == "%d" else float(default))
    )
whole = number_format == "%d"
value = st.number_input(
    _label(label, required),
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
    _problem(validation_message)
