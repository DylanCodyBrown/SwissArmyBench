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
import streamlit as st
from sab_canvas import In, Out, Table, key, sample

# The tickets table (empty: made-up sample data)
table_name: In[Table] = None
id_column = "ticket_id"  # column of table_name
status_column = "status"  # column of table_name
priority_column = "priority"  # column of table_name
opened_column = "opened_at"  # column of table_name
# The statuses shown at first
open_statuses = ["New", "Open", "Waiting on customer"]
# Most urgent first: the priorities in order
priority_order = ["Urgent", "High", "Normal", "Low"]
# The picked ticket's id, for the page's ticket widgets (they read it by themselves)
ticket_id: Out[int] = None


frame = table_name if table_name is not None else sample(kind="tickets")
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
        ticket_id = value.item() if hasattr(value, "item") else value
