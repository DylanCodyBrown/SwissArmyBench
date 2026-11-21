# /// swissarmybench-widget
# format = 1
# name = "input_radio"
# description = "Pick one of a few, all shown"
# framework = "streamlit"
# group = "Inputs"
# pack = "User inputs"
# tags = []
# size = [3, 2]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import key

# The words above the input
label = "Delivery"
# Shown beside the label as a ?
help_text = ""
# The choices
options = ["Standard", "Express", "Collect in store"]
# The choice at the start (empty: none)
default = "Standard"
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The session state key the value is kept under (empty: this widget's own)
state_key = ""
# Said under the input while it is required and missing, or does not fit
validation_message = "Choose one."
# The choices side by side
horizontal = False


def _label(text, needed):
    """The pack's one required marker: a red star after the label."""
    return f"{text} :red[\\*]" if needed else text


def _problem(message):
    """The pack's one error look, under the input."""
    st.markdown(f":red[{message}]")


_key = state_key or key("value")
if _key not in st.session_state:
    st.session_state[_key] = default if default in options else None
value = st.radio(
    _label(label, required),
    options,
    key=_key,
    horizontal=horizontal,
    help=help_text or None,
    disabled=disabled,
)
if required and value is None:
    _problem(validation_message)
