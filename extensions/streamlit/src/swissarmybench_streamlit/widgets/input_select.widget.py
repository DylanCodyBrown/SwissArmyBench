# /// swissarmybench-widget
# format = 1
# name = "input_select"
# description = "Pick one from a list"
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
label = "Region"
# Shown beside the label as a ?
help_text = ""
# Shown in the box while it is empty
placeholder = "Choose an option"
# The choices
options = ["North", "South", "East", "West"]
# The choice at the start (empty: none)
default = ""
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The session state key the value is kept under (empty: this widget's own)
state_key = ""
# Said under the input while it is required and missing, or does not fit
validation_message = "Choose one."
# The viewer may type a choice that is not in the list
accept_new = False


def _label(text, needed):
    """The pack's one required marker: a red star after the label."""
    return f"{text} :red[\\*]" if needed else text


def _problem(message):
    """The pack's one error look, under the input."""
    st.markdown(f":red[{message}]")


_key = state_key or key("value")
if _key not in st.session_state:
    st.session_state[_key] = default if default in options else None
value = st.selectbox(
    _label(label, required),
    options,
    key=_key,
    accept_new_options=accept_new,
    help=help_text or None,
    placeholder=placeholder or None,
    disabled=disabled,
)
if required and value is None:
    _problem(validation_message)
