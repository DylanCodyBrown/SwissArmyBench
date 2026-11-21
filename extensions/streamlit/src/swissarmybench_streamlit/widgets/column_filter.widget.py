# /// swissarmybench-widget
# format = 1
# name = "column_filter"
# description = "A filter other widgets read: one value of a column"
# framework = "streamlit"
# group = "Filters"
# tags = []
# size = [3, 1]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import key, table

# The table to show (empty: made-up sample data)
table_name = ""  # table
column = "region"  # column of table_name
label = "Region"
# The session state key other widgets read (filtered_table reads it)
state_key = "filter"

frame = table(table_name)
values = sorted(frame[column].dropna().astype(str).unique()) if column in frame.columns else []
st.selectbox(label, ["All", *values], key=state_key or key("filter"))
