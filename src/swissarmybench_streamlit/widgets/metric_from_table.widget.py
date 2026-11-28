# /// swissarmybench-widget
# format = 1
# name = "metric_from_table"
# description = "A column's total from a table"
# framework = "streamlit"
# group = "Data"
# tags = []
# size = [3, 2]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import In, Table, sample

# The table to show (empty: made-up sample data)
table_name: In[Table] = None
label = "Total revenue"
column = "revenue"  # column of table_name
how = "sum"  # choices: sum, mean, max, min, count

frame = table_name if table_name is not None else sample()
if column in frame.columns:
    found = getattr(frame[column], how)()
    st.metric(label, f"{found:,.0f}" if isinstance(found, (int, float)) else found)
else:
    st.metric(label, "—")
