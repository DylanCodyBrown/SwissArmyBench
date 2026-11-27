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
from datetime import date

import streamlit as st
from sab_canvas import Out, key

label = "Period"
start = "2026-01-01"
end = "2026-12-31"
# The first and last day picked, for the widgets on the page that read them
period: Out[list[date]] = None

period = list(
    st.date_input(
        label,
        (datetime.date.fromisoformat(start), datetime.date.fromisoformat(end)),
        key=key("period"),
    )
)
