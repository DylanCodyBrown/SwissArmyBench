# /// swissarmybench-widget
# format = 1
# name = "date_filter"
# description = "A date range other widgets read"
# framework = "streamlit"
# group = "Filters"
# tags = []
# size = [4, 1]
# min_size = [2, 1]
# ///
import datetime

import streamlit as st
from sab_canvas import key

label = "Period"
start = "2026-01-01"
end = "2026-12-31"
state_key = "period"

st.date_input(
    label,
    (datetime.date.fromisoformat(start), datetime.date.fromisoformat(end)),
    key=state_key or key("period"),
)
