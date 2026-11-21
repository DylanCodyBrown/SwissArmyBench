# /// swissarmybench-widget
# format = 1
# name = "input_text"
# description = "One line of text or a password, with a length limit and a pattern"
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
label = "Name"
# Shown beside the label as a ?
help_text = ""
# Shown in the box while it is empty
placeholder = "Type here"
default = ""
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The session state key the value is kept under (empty: this widget's own)
state_key = ""
# Said under the input while it is required and missing, or does not fit
validation_message = "Enter a value."
# Text, or a password shown as dots
kind = "default"  # choices: default, password
# The most characters (0: no limit)
max_chars: int = 0  # 0..100000
# A regular expression the value must match (empty: any text)
pattern = ""


def _label(text, needed):
    """The pack's one required marker: a red star after the label."""
    return f"{text} :red[\\*]" if needed else text


def _problem(message):
    """The pack's one error look, under the input."""
    st.markdown(f":red[{message}]")


_key = state_key or key("value")
if _key not in st.session_state:
    st.session_state[_key] = default
value = st.text_input(
    _label(label, required),
    key=_key,
    type=kind,
    max_chars=max_chars or None,
    help=help_text or None,
    placeholder=placeholder or None,
    disabled=disabled,
)
if required and not value.strip():
    _problem(validation_message)
elif pattern and value:
    import re

    if not re.fullmatch(pattern, value):
        _problem(validation_message)
