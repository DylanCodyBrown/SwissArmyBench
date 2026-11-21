# /// swissarmybench-widget
# format = 1
# name = "histogram"
# description = "How a column's values spread"
# framework = "streamlit"
# group = "Charts"
# tags = []
# size = [6, 4]
# min_size = [3, 2]
# ///
import altair as alt
import streamlit as st
from sab_canvas import In, Table, key, sample

# The table to show (empty: made-up sample data)
table_name: In[Table] = None
column = "revenue"  # column of table_name
bins = 12  # 2..100
colour = "#6a51a3"

frame = table_name if table_name is not None else sample()
chart = alt.Chart(frame).mark_bar(color=colour).encode(alt.X(column, bin=alt.Bin(maxbins=bins)), y="count()")
st.altair_chart(chart, use_container_width=True, key=key("chart"))
