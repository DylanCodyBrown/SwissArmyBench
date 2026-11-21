# /// swissarmybench-widget
# format = 1
# name = "search_box"
# description = "Search a table's rows as you type"
# framework = "streamlit"
# group = "Inputs"
# tags = []
# size = [6, 3]
# min_size = [3, 2]
# ///
import streamlit as st
from sab_canvas import key, table

# The table to search (empty: made-up sample data)
table_name = ""  # table
placeholder = "Search"

frame = table(table_name)
words = st.text_input("Search", placeholder=placeholder, key=key("search"), label_visibility="collapsed")
if words:
    found = frame.astype(str).apply(lambda column: column.str.contains(words, case=False, regex=False))
    frame = frame[found.any(axis=1)]
st.dataframe(frame, use_container_width=True, hide_index=True)
