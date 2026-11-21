# /// swissarmybench-widget
# format = 1
# name = "data_table"
# description = "A table, searchable and sortable"
# framework = "streamlit"
# group = "Data"
# tags = []
# size = [6, 4]
# min_size = [2, 2]
# ///
import streamlit as st
from sab_canvas import In, Table, key, sample

# The table to show (empty: made-up sample data)
table_name: In[Table] = None
# Rows shown at most
rows = 200  # 1..10000
show_index = False

frame = table_name if table_name is not None else sample()
st.dataframe(frame.head(rows), use_container_width=True, hide_index=not show_index, key=key("table"))
