# /// swissarmybench-widget
# format = 1
# name = "stacked_bars"
# description = "Bars split by a category"
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
group = "region"  # column of table_name

frame = table(table_name)
chart = alt.Chart(frame).mark_bar().encode(x=x, y=f"sum({y})", color=group)
st.altair_chart(chart, use_container_width=True, key=key("chart"))
