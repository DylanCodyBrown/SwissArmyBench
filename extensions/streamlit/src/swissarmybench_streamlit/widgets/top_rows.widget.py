# /// swissarmybench-widget
# format = 1
# name = "top_rows"
# description = "The top rows of a table by a column"
# framework = "streamlit"
# group = "Data"
# tags = []
# size = [5, 3]
# min_size = [2, 2]
# ///
import streamlit as st
from sab_canvas import table

# The table to show (empty: made-up sample data)
table_name = ""  # table
# The column to rank by
by = "revenue"  # column of table_name
count = 5  # 1..100

frame = table(table_name)
if by in frame.columns:
    frame = frame.sort_values(by, ascending=False)
st.dataframe(frame.head(count), use_container_width=True, hide_index=True)
