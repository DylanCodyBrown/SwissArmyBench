# /// swissarmybench-widget
# format = 1
# name = "date_range"
# description = "A start and an end date"
# framework = "streamlit"
# group = "Inputs"
# tags = []
# size = [4, 1]
# min_size = [2, 1]
# ///
import datetime

import streamlit as st
from sab_canvas import key

label = "Dates"
start = "2026-01-01"
end = "2026-03-31"
state_key = "dates"

first = datetime.date.fromisoformat(start)
last = datetime.date.fromisoformat(end)
st.date_input(label, (first, max(first, last)), key=state_key or key("dates"))
