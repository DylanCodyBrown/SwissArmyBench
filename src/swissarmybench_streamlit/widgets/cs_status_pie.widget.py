# /// swissarmybench-widget
# format = 1
# name = "cs_status_pie"
# description = "Tickets by status as a pie or a ring"
# framework = "streamlit"
# group = "Charts"
# pack = "Customer service"
# tags = []
# size = [4, 4]
# min_size = [2, 2]
# ///
import altair as alt
import streamlit as st
from sab_canvas import In, Table, key, sample

# The tickets table (empty: made-up sample data)
table_name: In[Table] = None
status_column = "status"  # column of table_name
title = "Tickets by status"
# A ring instead of a full pie
ring = True


frame = table_name if table_name is not None else sample(kind="tickets")
if status_column not in frame.columns:
    st.warning(f"Pick the status column: {status_column} is not in the table.")
else:
    counts = frame[status_column].astype(str).value_counts().rename_axis("status").reset_index(name="tickets")
    chart = (
        alt.Chart(counts, title=title or alt.Undefined)
        .mark_arc(innerRadius=50 if ring else 0)
        .encode(theta="tickets:Q", color=alt.Color("status:N", title=None), tooltip=["status", "tickets"])
    )
    st.altair_chart(chart, use_container_width=True, key=key("chart"))
