# /// swissarmybench-widget
# format = 1
# name = "donut_chart"
# description = "Shares of a whole, with a hole"
# framework = "streamlit"
# group = "Charts"
# tags = []
# size = [4, 4]
# min_size = [3, 3]
# ///
import altair as alt
import streamlit as st
from sab_canvas import In, Table, key, sample

# The table to show (empty: made-up sample data)
table_name: In[Table] = None
category = "product"  # column of table_name
amount = "revenue"  # column of table_name
hole = 50  # 10..120

frame = table_name if table_name is not None else sample()
chart = alt.Chart(frame).mark_arc(innerRadius=hole).encode(theta=f"sum({amount})", color=category)
st.altair_chart(chart, use_container_width=True, key=key("chart"))
