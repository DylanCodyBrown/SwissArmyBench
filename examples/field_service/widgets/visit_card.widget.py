# /// swissarmybench-widget
# format = 1
# name = "visit_card"
# description = "The visits to do for one technician; Mark done fires an event"
# framework = "streamlit"
# group = "Data"
# tags = ["field service"]
# size = [6, 6]
# min_size = [3, 3]
# ///
from typing import Literal, TypedDict

import streamlit as st
from sab_canvas import Event, In, Out, Table, key, sample


class Visit(TypedDict):
    work_order_id: int
    technician: str
    note: str


# The work orders (not wired: made-up sample data)
orders: In[Table] = None
# The technicians, to find the picked one's work orders by name (not wired: everyone's)
technicians: In[Table] = None
# The technician whose visits show (wired from a select; All: everyone's)
technician: In[str] = "All"
# Who is looking at the page
viewer: In[str] = "unknown"
heading = "Visits to do"
accent = "#0b6e4f"
# How many visits it lists
max_rows = 6  # 1..50
# Show the ones already done too
show_done = False
# The status a visit to do has
status: Literal["open", "scheduled", "in_progress"] = "scheduled"
id_column = "work_order_id"  # column of orders
# The visit picked, for the other widgets (another page's too)
picked: Out[int] = None
# Fired by Mark done: the visit (work_order_id, technician, note); the Canvas wires what it does
completed: Event[Visit] = None

frame = orders if orders is not None else sample(kind="tickets")
who = technician or "All"
st.markdown(f"<h4 style='color:{accent};margin:0'>{heading}</h4>", unsafe_allow_html=True)
st.caption(f"For {viewer} · technician: {who}")
if "status" in frame.columns and not show_done:
    frame = frame[frame["status"].astype(str) == status]
if who != "All" and technicians is not None and "technician_id" in frame.columns:
    ids = technicians[technicians["name"].astype(str) == who]["technician_id"]
    frame = frame[frame["technician_id"].isin(list(ids))]
frame = frame.head(max_rows)
if id_column not in frame.columns:
    st.warning(f"Pick the visit's id column: {id_column} is not in the table.")
elif frame.empty:
    st.info("No visits to do.")
else:
    visits = [v.item() if hasattr(v, "item") else v for v in frame[id_column]]
    chosen = st.selectbox("Visit", visits, key=key("visit"))
    picked = chosen
    st.dataframe(frame, hide_index=True, use_container_width=True)
    note = st.text_input("Note", key=key("note"))
    if st.button("Mark done", type="primary", key=key("done")):
        completed({"work_order_id": int(chosen), "technician": who, "note": note})
        st.success(f"Visit {chosen} marked done.")
