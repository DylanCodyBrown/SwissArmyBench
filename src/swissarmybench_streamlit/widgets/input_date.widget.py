# /// swissarmybench-widget
# format = 1
# name = "input_date"
# description = "One date between an earliest and a latest"
# framework = "streamlit"
# group = "Inputs"
# pack = "User inputs"
# tags = []
# size = [3, 1]
# min_size = [2, 1]
# ///
import datetime
from datetime import date

import streamlit as st
from sab_canvas import In, Out, key, marked, problem

# The words above the input
label = "Delivery date"
# Shown beside the label as a ?
help_text = ""
# The starting date (empty: none)
default = ""  # date
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The value, for the widgets on the page that read it
value: Out[date] = None
# Its starting value from another widget (not wired: default above)
default_from: In[date] = None
# Said under the input while it is required and missing, or does not fit
validation_message = "Pick a date in range."
# The earliest and latest dates allowed (empty: no limit)
earliest = ""  # date
latest = ""  # date
date_format = "YYYY/MM/DD"  # choices: YYYY/MM/DD, DD/MM/YYYY, MM/DD/YYYY


def _date(text):
    return datetime.date.fromisoformat(text) if text else None


if default_from is not None:
    default = default_from.isoformat()
_key = key("value")
if _key not in st.session_state:
    st.session_state[_key] = _date(default)
value = st.date_input(
    marked(label, required),
    key=_key,
    min_value=_date(earliest),
    max_value=_date(latest),
    format=date_format,
    help=help_text or None,
    disabled=disabled,
)
if required and value is None:
    problem(validation_message)
