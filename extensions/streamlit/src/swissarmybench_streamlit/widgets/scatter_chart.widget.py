# /// swissarmybench-widget
# format = 1
# name = "scatter_chart"
# description = "Points: one column against another"
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
x = "units"  # column of table_name
y = "revenue"  # column of table_name
group = "region"  # column of table_name
size = 60  # 10..400

frame = table(table_name)
encoding = {"x": x, "y": y}
if group in frame.columns:
    encoding["color"] = group
chart = alt.Chart(frame).mark_circle(size=size).encode(**encoding)
st.altair_chart(chart, use_container_width=True, key=key("chart"))
