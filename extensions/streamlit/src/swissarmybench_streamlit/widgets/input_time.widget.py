# /// swissarmybench-widget
# format = 1
# name = "input_time"
# description = "A time of day, in steps"
# framework = "streamlit"
# group = "Inputs"
# pack = "User inputs"
# tags = []
# size = [3, 1]
# min_size = [2, 1]
# ///
import datetime

import streamlit as st
from sab_canvas import key

# The words above the input
label = "Start time"
# Shown beside the label as a ?
help_text = ""
# The starting time (empty: none)
default = "09:00"  # time
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The session state key the value is kept under (empty: this widget's own)
state_key = ""
# Said under the input while it is required and missing, or does not fit
validation_message = "Pick a time."
# The minutes between choices
step_minutes: int = 15  # 1..1440


def _label(text, needed):
    """The pack's one required marker: a red star after the label."""
    return f"{text} :red[\\*]" if needed else text


def _problem(message):
    """The pack's one error look, under the input."""
    st.markdown(f":red[{message}]")


_key = state_key or key("value")
if _key not in st.session_state:
    st.session_state[_key] = datetime.time.fromisoformat(default) if default else None
value = st.time_input(
    _label(label, required),
    key=_key,
    step=datetime.timedelta(minutes=max(1, int(step_minutes))),
    help=help_text or None,
    disabled=disabled,
)
if required and value is None:
    _problem(validation_message)
