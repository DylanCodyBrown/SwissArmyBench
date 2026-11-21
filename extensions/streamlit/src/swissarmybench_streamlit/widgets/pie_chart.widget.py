# /// swissarmybench-widget
# format = 1
# name = "pie_chart"
# description = "Shares of a whole"
# framework = "streamlit"
# group = "Charts"
# tags = []
# size = [4, 4]
# min_size = [3, 3]
# ///
import altair as alt
import streamlit as st
from sab_canvas import key, table

# The table to show (empty: made-up sample data)
table_name = ""  # table
category = "region"  # column of table_name
amount = "revenue"  # column of table_name

frame = table(table_name)
chart = alt.Chart(frame).mark_arc().encode(theta=f"sum({amount})", color=category)
st.altair_chart(chart, use_container_width=True, key=key("chart"))
