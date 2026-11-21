# /// swissarmybench-widget
# format = 1
# name = "input_multiselect"
# description = "Pick several from a list"
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
label = "Regions"
# Shown beside the label as a ?
help_text = ""
# Shown in the box while it is empty
placeholder = "Choose options"
# The choices
options = ["North", "South", "East", "West"]
# The choices picked at the start
default = ["North"]
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The session state key the value is kept under (empty: this widget's own)
state_key = ""
# Said under the input while it is required and missing, or does not fit
validation_message = "Choose at least one."
# The most choices (0: no limit)
max_selections: int = 0  # 0..1000


def _label(text, needed):
    """The pack's one required marker: a red star after the label."""
    return f"{text} :red[\\*]" if needed else text


def _problem(message):
    """The pack's one error look, under the input."""
    st.markdown(f":red[{message}]")


_key = state_key or key("value")
if _key not in st.session_state:
    st.session_state[_key] = [d for d in default if d in options]
value = st.multiselect(
    _label(label, required),
    options,
    key=_key,
    max_selections=max_selections or None,
    help=help_text or None,
    placeholder=placeholder or None,
    disabled=disabled,
)
if required and not value:
    _problem(validation_message)
