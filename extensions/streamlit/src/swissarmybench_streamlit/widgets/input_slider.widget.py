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
from sab_canvas import key

# The words above the input
label = "Discount"
# Shown beside the label as a ?
help_text = ""
default: float = 10
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The session state key the value is kept under (empty: this widget's own)
state_key = ""
# Said under the input while it is required and missing, or does not fit
validation_message = "Pick a value in range."
minimum: float = 0
maximum: float = 100
step: float = 5
# How the value is shown (printf style: %d, %.1f%%, €%d)
number_format = "%d%%"


def _label(text, needed):
    """The pack's one required marker: a red star after the label."""
    return f"{text} :red[\\*]" if needed else text


def _problem(message):
    """The pack's one error look, under the input."""
    st.markdown(f":red[{message}]")


whole = all(float(v).is_integer() for v in (default, minimum, maximum, step))


def _number(v):
    return int(v) if whole else float(v)


_key = state_key or key("value")
if _key not in st.session_state:
    st.session_state[_key] = _number(default)
value = st.slider(
    _label(label, required),
    min_value=_number(minimum),
    max_value=_number(maximum),
    step=_number(step),
    format=number_format or None,
    key=_key,
    help=help_text or None,
    disabled=disabled,
)
if required and value is None:
    _problem(validation_message)
