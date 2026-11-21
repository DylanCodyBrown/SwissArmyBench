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
from sab_canvas import In, Out, Table, key, sample

# The table to show (empty: made-up sample data)
table_name: In[Table] = None
column = "region"  # column of table_name
label = "Region"
# The value picked (All: none), for the widgets on the page that read it (filtered_table)
filter: Out[str] = "All"

frame = table_name if table_name is not None else sample()
values = sorted(frame[column].dropna().astype(str).unique()) if column in frame.columns else []
filter = st.selectbox(label, ["All", *values], key=key("filter"))
