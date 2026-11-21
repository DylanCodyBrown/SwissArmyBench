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
from datetime import date

import streamlit as st
from sab_canvas import Out, key

label = "Dates"
start = "2026-01-01"
end = "2026-03-31"
# The first and last day picked, for the widgets on the page that read them
dates: Out[list[date]] = None

first = datetime.date.fromisoformat(start)
last = datetime.date.fromisoformat(end)
dates = list(st.date_input(label, (first, max(first, last)), key=key("dates")))
