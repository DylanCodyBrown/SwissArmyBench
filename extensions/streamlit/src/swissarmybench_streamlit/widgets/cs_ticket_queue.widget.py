# /// swissarmybench-widget
# format = 1
# name = "cs_ticket_queue"
# description = "The open tickets, most urgent first; a click picks one"
# framework = "streamlit"
# group = "Data"
# pack = "Customer service"
# tags = []
# size = [8, 5]
# min_size = [4, 3]
# ///
import datetime

import pandas as pd
import streamlit as st
from sab_canvas import key, table

# The tickets table (empty: made-up sample data)
table_name = ""  # table
id_column = "ticket_id"  # column of table_name
status_column = "status"  # column of table_name
priority_column = "priority"  # column of table_name
opened_column = "opened_at"  # column of table_name
# The statuses shown at first
open_statuses = ["New", "Open", "Waiting on customer"]
# Most urgent first: the priorities in order
priority_order = ["Urgent", "High", "Normal", "Low"]
# The session state key the picked ticket's id is kept under (Ticket detail and Reply form read it)
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
if status_column not in frame.columns or id_column not in frame.columns:
    st.warning(f"Pick the ticket columns: {id_column} or {status_column} is not in the table.")
else:
    statuses = sorted(frame[status_column].dropna().astype(str).unique())
    shown_statuses = st.multiselect(
        "Status", statuses, default=[s for s in open_statuses if s in statuses], key=key("status")
    )
    queue = frame[frame[status_column].astype(str).isin(shown_statuses)] if shown_statuses else frame
    if priority_column in queue.columns:
        rank = {p: at for at, p in enumerate(priority_order)}
        queue = queue.assign(_rank=queue[priority_column].map(rank).fillna(len(rank)))
        queue = queue.sort_values(
            ["_rank", opened_column] if opened_column in queue.columns else ["_rank"]
        ).drop(columns="_rank")
    st.caption(f"{len(queue)} tickets")
    picked = st.dataframe(
        queue,
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key=key("queue"),
    )
    rows = getattr(getattr(picked, "selection", None), "rows", []) or []
    if rows:
        value = queue.iloc[rows[0]][id_column]
        st.session_state[selected_key] = value.item() if hasattr(value, "item") else value
