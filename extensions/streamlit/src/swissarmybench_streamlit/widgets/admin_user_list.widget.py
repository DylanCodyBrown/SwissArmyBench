# /// swissarmybench-widget
# format = 1
# name = "admin_user_list"
# description = "The users with search, a role filter and active only"
# framework = "streamlit"
# group = "Data"
# pack = "Admin"
# tags = []
# size = [8, 5]
# min_size = [4, 3]
# ///

import pandas as pd
import streamlit as st
from sab_canvas import key, table

# The users table (empty: made-up sample data)
table_name = ""  # table
name_column = "name"  # column of table_name
role_column = "role"  # column of table_name
active_column = "active"  # column of table_name
# Show only active users at first
active_only = True


def _sample():
    """Made-up users at example.com."""
    first = ["Ada", "Bram", "Cleo", "Dov", "Esme", "Finn", "Greta", "Hugo", "Ines", "Jory"]
    roles = ["Admin", "Editor", "Viewer", "Viewer", "Editor"]
    return pd.DataFrame(
        [
            {
                "user_id": 1 + at,
                "name": f"{name} Larkfield",
                "email": f"{name.lower()}@example.com",
                "role": roles[at % 5],
                "active": at % 7 != 3,
                "last_sign_in": pd.Timestamp(2026, 11, 1 + at, 9, 30),
            }
            for at, name in enumerate(first)
        ]
    )


frame = table(table_name) if table_name else _sample()
left, middle, right = st.columns([3, 2, 1])
words = left.text_input("Search", placeholder="Name or email", key=key("search"))
roles = sorted(frame[role_column].dropna().astype(str).unique()) if role_column in frame.columns else []
picked = middle.multiselect("Role", roles, placeholder="All", key=key("roles"))
only = right.toggle("Active", active_only, key=key("active"))
shown = frame
if words:
    text = shown.astype(str).agg(" ".join, axis=1).str.lower()
    shown = shown[text.str.contains(words.lower(), regex=False)]
if picked and role_column in shown.columns:
    shown = shown[shown[role_column].astype(str).isin(picked)]
if only and active_column in shown.columns:
    shown = shown[shown[active_column].astype(bool)]
st.caption(f"{len(shown)} of {len(frame)} users")
st.dataframe(shown, hide_index=True, use_container_width=True)
