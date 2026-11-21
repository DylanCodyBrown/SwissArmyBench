# /// swissarmybench-widget
# format = 1
# name = "filtered_table"
# description = "A table that follows a filter's session key"
# framework = "streamlit"
# group = "Filters"
# tags = []
# size = [6, 4]
# min_size = [2, 2]
# ///
import streamlit as st
from sab_canvas import table

# The table to show (empty: made-up sample data)
table_name = ""  # table
column = "region"  # column of table_name
# The filter's session state key
state_key = "filter"

frame = table(table_name)
picked = st.session_state.get(state_key, "All")
if picked not in (None, "All") and column in frame.columns:
    frame = frame[frame[column].astype(str) == str(picked)]
st.caption(f"{len(frame)} rows" + ("" if picked in (None, "All") else f" where {column} is {picked}"))
st.dataframe(frame, use_container_width=True, hide_index=True)
