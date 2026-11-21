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
from sab_canvas import key

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
# The session state key the value is kept under (empty: this widget's own)
state_key = ""
# Said under the input while it is required and missing, or does not fit
validation_message = "Enter some text."
# The box's height in pixels
height: int = 120  # 68..800
# The most characters (0: no limit)
max_chars: int = 0  # 0..100000


def _label(text, needed):
    """The pack's one required marker: a red star after the label."""
    return f"{text} :red[\\*]" if needed else text


def _problem(message):
    """The pack's one error look, under the input."""
    st.markdown(f":red[{message}]")


_key = state_key or key("value")
if _key not in st.session_state:
    st.session_state[_key] = default
value = st.text_area(
    _label(label, required),
    key=_key,
    height=height,
    max_chars=max_chars or None,
    help=help_text or None,
    placeholder=placeholder or None,
    disabled=disabled,
)
if required and not value.strip():
    _problem(validation_message)
