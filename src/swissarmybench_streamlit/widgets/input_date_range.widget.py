# /// swissarmybench-widget
# format = 1
# name = "input_date_range"
# description = "A first and a last day"
# framework = "streamlit"
# group = "Inputs"
# pack = "User inputs"
# tags = []
# size = [4, 1]
# min_size = [2, 1]
# ///
import datetime
from datetime import date

import streamlit as st
from sab_canvas import Out, key, marked, problem

# The words above the input
label = "Dates"
# Shown beside the label as a ?
help_text = ""
# The first and last days at the start
start = "2026-11-01"  # date
end = "2026-11-30"  # date
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The value, for the widgets on the page that read it
value: Out[list[date]] = None
# Said under the input while it is required and missing, or does not fit
validation_message = "Pick a first and a last day."
earliest = ""  # date
latest = ""  # date
date_format = "YYYY/MM/DD"  # choices: YYYY/MM/DD, DD/MM/YYYY, MM/DD/YYYY


def _date(text):
    return datetime.date.fromisoformat(text) if text else None


_key = key("value")
if _key not in st.session_state:
    st.session_state[_key] = tuple(d for d in (_date(start), _date(end)) if d)
value = st.date_input(
    marked(label, required),
    key=_key,
    min_value=_date(earliest),
    max_value=_date(latest),
    format=date_format,
    help=help_text or None,
    disabled=disabled,
)
if required and (not isinstance(value, (tuple, list)) or len(value) != 2):
    problem(validation_message)
value = list(value) if value else []
