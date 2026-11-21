# /// swissarmybench-widget
# format = 1
# name = "cs_ticket_detail"
# description = "The picked ticket's subject and every field"
# framework = "streamlit"
# group = "Data"
# pack = "Customer service"
# tags = []
# size = [5, 4]
# min_size = [3, 2]
# ///
import datetime

import pandas as pd
import streamlit as st
from sab_canvas import table

# The tickets table (empty: made-up sample data)
table_name = ""  # table
id_column = "ticket_id"  # column of table_name
subject_column = "subject"  # column of table_name
# The session state key the queue keeps the picked ticket's id under (none picked: the first ticket)
selected_key = "ticket"


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
if id_column not in frame.columns or frame.empty:
    st.warning(f"Pick the ticket table: {id_column} is not in it, or it has no rows.")
else:
    wanted = st.session_state.get(selected_key)
    found = frame[frame[id_column].astype(str) == str(wanted)] if wanted is not None else frame.iloc[0:0]
    ticket = (found if len(found) else frame).iloc[0]
    st.subheader(f"#{ticket[id_column]} {ticket[subject_column] if subject_column in frame.columns else ''}")
    facts = [(c, ticket[c]) for c in frame.columns if c not in (id_column, subject_column)]
    left, right = st.columns(2)
    for at, (name, value) in enumerate(facts):
        shown = (
            "—"
            if pd.isna(value)
            else (value.strftime("%Y-%m-%d %H:%M") if hasattr(value, "strftime") else value)
        )
        (left if at % 2 == 0 else right).markdown(f"**{name.replace('_', ' ').capitalize()}**  \n{shown}")
