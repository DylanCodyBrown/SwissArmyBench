# /// swissarmybench-widget
# format = 1
# name = "sales_filter_bar"
# description = "Regions and dates that filter the other Sales widgets"
# framework = "streamlit"
# group = "Filters"
# pack = "Sales dashboard"
# tags = []
# size = [12, 2]
# min_size = [6, 1]
# ///
import datetime

import pandas as pd
import streamlit as st
from sab_canvas import key, table

# The table its choices come from (empty: made-up sample data)
table_name = ""  # table
region_column = "region"  # column of table_name
date_column = "month"  # column of table_name
region_label = "Regions"
date_label = "Dates"
# The session state key the picks are kept under (the other Sales widgets read it)
filter_key = "sales_filter"

frame = table(table_name)
regions_key, dates_key = key("regions"), key("dates")


def _keep():
    """The picks kept under filter_key: run as a pick changes, so every widget of the page sees them on
    this run, whichever is drawn first."""
    chosen = st.session_state.get(dates_key)
    start, end = chosen if isinstance(chosen, (tuple, list)) and len(chosen) == 2 else (None, None)
    st.session_state[filter_key] = {
        "region_column": region_column,
        "regions": list(st.session_state.get(regions_key) or []),
        "date_column": date_column,
        "start": start.isoformat() if isinstance(start, datetime.date) else None,
        "end": end.isoformat() if isinstance(end, datetime.date) else None,
    }


left, right = st.columns([3, 2])
regions = sorted(frame[region_column].dropna().astype(str).unique()) if region_column in frame.columns else []
left.multiselect(region_label, regions, placeholder="All", key=regions_key, on_change=_keep)
if date_column in frame.columns:
    dates = pd.to_datetime(frame[date_column], errors="coerce").dropna()
    if len(dates):
        first, last = dates.min().date(), dates.max().date()
        right.date_input(
            date_label, (first, last), min_value=first, max_value=last, key=dates_key, on_change=_keep
        )
if filter_key not in st.session_state:
    _keep()
