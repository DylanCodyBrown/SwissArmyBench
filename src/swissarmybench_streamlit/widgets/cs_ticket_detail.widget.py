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
import pandas as pd
import streamlit as st
from sab_canvas import In, Table, sample

# The tickets table (empty: made-up sample data)
table_name: In[Table] = None
id_column = "ticket_id"  # column of table_name
subject_column = "subject"  # column of table_name
# The ticket to show: the queue's picked ticket_id, wired by itself (none: the first)
ticket_id: In[int] = None


frame = table_name if table_name is not None else sample(kind="tickets")
if id_column not in frame.columns or frame.empty:
    st.warning(f"Pick the ticket table: {id_column} is not in it, or it has no rows.")
else:
    wanted = ticket_id
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
