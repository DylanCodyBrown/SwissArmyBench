# /// swissarmybench-blade
# format = 1
# name = "Streamlit date range filter"
# kind = "snippet"
# description = "Pick a first and a last day; only the rows between go on"
# tags = ["streamlit", "filter", "dates"]
# family = "Streamlit"
# language = "streamlit"
# cell_name = "<<label>> filter"
# ///
snippet = r"""
# Date range filter: pick a first and a last day on a calendar; only the rows between go on.
#
# Makes: <<name: in_{date column}>>
#   the rows of <<table>> whose <<date column>> is from the first day to the last
# Reads: <<table>>
#   a table: an open one, or the rows another filter left
#
# Streamlit functions:
#   st.date_input(label, value)   a calendar; given two days, it gives back the two picked
#
# Each pick reruns the whole page from the top, so every piece that reads <<name>> shows the
# rows for what is picked now.
import pandas as pd
import streamlit as st

_days = pd.to_datetime(<<table>>["<<date column>>"]).dt.date  # each row's day (no time of day)
# key= gives the widget a name of its own on the page: two widgets with the same label would
# otherwise be taken for one, and Streamlit would stop with a "duplicate widget" error.
_range = st.date_input(
    "<<label>>",
    value=(_days.min(), _days.max()),
    key="<<name>>_pick",
)
# While only the first day is picked, the range has one end: every row stays until the second.
if isinstance(_range, tuple) and len(_range) == 2:
    <<name>> = <<table>>[_days.between(_range[0], _range[1])]
else:
    <<name>> = <<table>>
"""
