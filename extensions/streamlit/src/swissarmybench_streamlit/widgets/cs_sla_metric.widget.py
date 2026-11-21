# /// swissarmybench-widget
# format = 1
# name = "cs_sla_metric"
# description = "The share of tickets answered within their SLA"
# framework = "streamlit"
# group = "Data"
# pack = "Customer service"
# tags = []
# size = [3, 2]
# min_size = [2, 1]
# ///
import datetime

import pandas as pd
import streamlit as st
from sab_canvas import table

# The tickets table (empty: made-up sample data)
table_name = ""  # table
response_column = "first_response_minutes"  # column of table_name
sla_column = "sla_hours"  # column of table_name
label = "First response within SLA"
# The share you aim to meet
target: float = 0.9  # 0..1 step 0.01


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
if response_column not in frame.columns or sla_column not in frame.columns:
    st.warning(f"Pick the SLA columns: {response_column} or {sla_column} is not in the table.")
else:
    minutes = pd.to_numeric(frame[response_column], errors="coerce")
    allowed = pd.to_numeric(frame[sla_column], errors="coerce") * 60
    known = minutes.notna() & allowed.notna()
    met = int((minutes[known] <= allowed[known]).sum())
    share = met / int(known.sum()) if known.any() else 0.0
    st.metric(label, f"{share:.0%}", f"{share - target:+.0%} against the {target:.0%} target")
    st.caption(f"{met} of {int(known.sum())} tickets answered within their service level agreement")
