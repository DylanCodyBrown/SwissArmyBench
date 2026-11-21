# /// swissarmybench-widget
# format = 1
# name = "sparkline"
# description = "A tiny line of a column"
# framework = "streamlit"
# group = "Charts"
# tags = []
# size = [3, 1]
# min_size = [2, 1]
# ///
import altair as alt
import streamlit as st
from sab_canvas import key, table

# The table to show (empty: made-up sample data)
table_name = ""  # table
y = "revenue"  # column of table_name
colour = "#1f77b4"

frame = table(table_name).reset_index()
chart = (
    alt.Chart(frame, height=60)
    .mark_line(color=colour)
    .encode(x=alt.X("index", axis=None), y=alt.Y(y, axis=None))
)
st.altair_chart(chart, use_container_width=True, key=key("chart"))
