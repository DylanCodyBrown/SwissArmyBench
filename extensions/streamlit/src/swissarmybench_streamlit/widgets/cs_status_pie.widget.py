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
import datetime

import altair as alt
import pandas as pd
import streamlit as st
from sab_canvas import key, table

# The tickets table (empty: made-up sample data)
table_name = ""  # table
status_column = "status"  # column of table_name
title = "Tickets by status"
# A ring instead of a full pie
ring = True


def _sample():
    """Made-up tickets (the shape of support_tickets, with the customer's name)."""
    subjects = [
        "Where is my order?",
        "Item arrived damaged",
        "Wrong item sent",
        "Refund not received",
        "Change delivery address",
        "Invoice copy please",
        "Product question",
        "Missing part",
    ]
    people = [
        "Ada Ashdown",
        "Bram Brookfield",
        "Cleo Calloway",
        "Dov Dunmore",
        "Esme Everly",
        "Finn Fairbank",
    ]
    statuses = ["New", "Open", "Waiting on customer", "Open", "Resolved", "Closed"]
    priorities = ["Normal", "High", "Low", "Urgent", "Normal", "Normal"]
    hours = {"Urgent": 4, "High": 8, "Normal": 24, "Low": 72}
    start = datetime.datetime(2026, 10, 20, 8, 0)
    rows = []
    for at in range(18):
        priority = priorities[at % 6]
        status = statuses[(at * 5) % 6]
        opened = start + datetime.timedelta(hours=at * 7)
        rows.append(
            {
                "ticket_id": 9100 + at,
                "customer_name": people[at % 6],
                "subject": subjects[at % 8],
                "priority": priority,
                "status": status,
                "channel": ["Email", "Chat", "Phone"][at % 3],
                "opened_at": opened,
                "closed_at": opened + datetime.timedelta(hours=5 + at)
                if status in ("Resolved", "Closed")
                else None,
                "sla_hours": hours[priority],
                "first_response_minutes": (at * 97) % 1500 + 5,
            }
        )
    frame = pd.DataFrame(rows)
    frame["closed_at"] = pd.to_datetime(frame["closed_at"])
    return frame


frame = table(table_name) if table_name else _sample()
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
