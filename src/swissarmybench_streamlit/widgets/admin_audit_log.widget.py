# /// swissarmybench-widget
# format = 1
# name = "admin_audit_log"
# description = "Who did what and when, newest first, filtered and downloadable"
# framework = "streamlit"
# group = "Data"
# pack = "Admin"
# tags = []
# size = [8, 5]
# min_size = [4, 3]
# ///
import pandas as pd
import streamlit as st
from sab_canvas import In, Table, key

# The audit log (empty: made-up sample data)
table_name: In[Table] = None
time_column = "at"  # column of table_name
user_column = "user"  # column of table_name
action_column = "action"  # column of table_name
# How many rows at most
rows: int = 100  # 1..5000
file_name = "audit-log.csv"


def _sample():
    """Made-up audit entries."""
    users = ["ada@example.com", "bram@example.com", "cleo@example.com"]
    actions = [
        "signed in",
        "edited a record",
        "approved",
        "exported a table",
        "changed a setting",
        "rejected",
    ]
    objects = ["product 104", "order 81012", "Settings", "customers", "ticket 9105", "product 101"]
    start = pd.Timestamp(2026, 11, 20, 8, 0)
    return pd.DataFrame(
        [
            {
                "at": start + pd.Timedelta(minutes=at * 17),
                "user": users[at % 3],
                "action": actions[at % 6],
                "object": objects[(at * 5) % 6],
                "detail": f"made-up entry {at + 1}",
            }
            for at in range(30)
        ]
    )


frame = table_name if table_name is not None else _sample()
left, right = st.columns(2)
people = sorted(frame[user_column].dropna().astype(str).unique()) if user_column in frame.columns else []
actions = sorted(frame[action_column].dropna().astype(str).unique()) if action_column in frame.columns else []
who = left.multiselect("User", people, placeholder="Everyone", key=key("users"))
what = right.multiselect("Action", actions, placeholder="Every action", key=key("actions"))
shown = frame
if who:
    shown = shown[shown[user_column].astype(str).isin(who)]
if what:
    shown = shown[shown[action_column].astype(str).isin(what)]
if time_column in shown.columns:
    shown = shown.sort_values(time_column, ascending=False)
shown = shown.head(int(rows))
st.dataframe(shown, hide_index=True, use_container_width=True)
st.download_button(
    "Download",
    shown.to_csv(index=False).encode("utf-8"),
    file_name or "audit-log.csv",
    "text/csv",
    key=key("download"),
)
