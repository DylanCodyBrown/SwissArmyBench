# /// swissarmybench-widget
# format = 1
# name = "input_pills"
# description = "One or several choices as pills"
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
label = "Topics"
# Shown beside the label as a ?
help_text = ""
# The choices
options = ["Orders", "Returns", "Billing", "Delivery"]
# The choices picked at the start
default = []
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The session state key the value is kept under (empty: this widget's own)
state_key = ""
# Said under the input while it is required and missing, or does not fit
validation_message = "Choose at least one."
# One choice or several
selection_mode = "multi"  # choices: single, multi


def _label(text, needed):
    """The pack's one required marker: a red star after the label."""
    return f"{text} :red[\\*]" if needed else text


def _problem(message):
    """The pack's one error look, under the input."""
    st.markdown(f":red[{message}]")


_key = state_key or key("value")
if _key not in st.session_state:
    st.session_state[_key] = (
        (default[0] if default and default[0] in options else None)
        if selection_mode == "single"
        else [d for d in default if d in options]
    )
value = st.pills(
    _label(label, required),
    options,
    selection_mode=selection_mode,
    key=_key,
    help=help_text or None,
    disabled=disabled,
)
if required and not value:
    _problem(validation_message)
