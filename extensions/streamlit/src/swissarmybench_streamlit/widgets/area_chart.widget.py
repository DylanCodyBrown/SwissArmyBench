# /// swissarmybench-widget
# format = 1
# name = "area_chart"
# description = "An area over time from a table"
# framework = "streamlit"
# group = "Charts"
# tags = []
# size = [6, 4]
# min_size = [3, 2]
# ///
import altair as alt
import streamlit as st
from sab_canvas import key, table

# The table to show (empty: made-up sample data)
table_name = ""  # table
x = "month"  # column of table_name
y = "revenue"  # column of table_name
colour = "#1f77b4"
title = ""

frame = table(table_name)
chart = (
    (alt.Chart(frame, title=title) if title else alt.Chart(frame))
    .mark_area(color=colour, opacity=0.6)
    .encode(x=x, y=y)
)
st.altair_chart(chart, use_container_width=True, key=key("chart"))
