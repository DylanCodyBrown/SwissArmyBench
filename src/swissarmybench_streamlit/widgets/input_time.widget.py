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
from sab_canvas import In, Out, key, marked, problem

# The words above the input
label = "Start time"
# Shown beside the label as a ?
help_text = ""
# The starting time (empty: none)
default = "09:00"  # time
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The value, for the widgets on the page that read it
value: Out[str] = None
# Its starting value from another widget (not wired: default above)
default_from: In[str] = None
# Said under the input while it is required and missing, or does not fit
validation_message = "Pick a time."
# The minutes between choices
step_minutes: int = 15  # 1..1440


if default_from is not None:
    default = default_from
_key = key("value")
if _key not in st.session_state:
    st.session_state[_key] = datetime.time.fromisoformat(default) if default else None
value = st.time_input(
    marked(label, required),
    key=_key,
    step=datetime.timedelta(minutes=max(1, int(step_minutes))),
    help=help_text or None,
    disabled=disabled,
)
if required and value is None:
    problem(validation_message)
value = value.isoformat(timespec="minutes") if value is not None else None
