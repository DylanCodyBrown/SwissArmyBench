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
from sab_canvas import key

# The words above the input
label = "How was it?"
# Shown beside the label as a ?
help_text = ""
# The rating at the start, from 0 (-1: none)
default: int = -1  # -1..4
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The session state key the value is kept under (empty: this widget's own)
state_key = ""
# Said under the input while it is required and missing, or does not fit
validation_message = "Give a rating."
options = "thumbs"  # choices: thumbs, faces, stars


def _label(text, needed):
    """The pack's one required marker: a red star after the label."""
    return f"{text} :red[\\*]" if needed else text


def _problem(message):
    """The pack's one error look, under the input."""
    st.markdown(f":red[{message}]")


_key = state_key or key("value")
if _key not in st.session_state:
    st.session_state[_key] = None if default < 0 else int(default)
if label:
    st.markdown(_label(label, required), help=help_text or None)
value = st.feedback(options, key=_key, disabled=disabled)
if required and value is None:
    _problem(validation_message)
