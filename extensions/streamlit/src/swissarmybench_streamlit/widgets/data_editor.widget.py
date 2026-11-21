# /// swissarmybench-widget
# format = 1
# name = "data_editor"
# description = "A table the viewer can edit"
# framework = "streamlit"
# group = "Data"
# tags = []
# size = [6, 4]
# min_size = [2, 2]
# ///
import streamlit as st
from sab_canvas import key, table

# The table to show (empty: made-up sample data)
table_name = ""  # table
# Rows can be added and taken away
add_rows = True

frame = table(table_name)
st.data_editor(
    frame, num_rows="dynamic" if add_rows else "fixed", use_container_width=True, key=key("editor")
)
