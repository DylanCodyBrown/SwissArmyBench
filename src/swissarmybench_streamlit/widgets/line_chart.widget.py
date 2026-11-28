# /// swissarmybench-widget
# format = 1
# name = "line_chart"
# description = "A line over time from a table"
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
x = "month"  # column of table_name
y = "revenue"  # column of table_name
colour = "#1f77b4"
title = ""

frame = table_name if table_name is not None else sample()
chart = (
    (alt.Chart(frame, title=title) if title else alt.Chart(frame))
    .mark_line(color=colour, point=True)
    .encode(x=x, y=y)
)
st.altair_chart(chart, use_container_width=True, key=key("chart"))
