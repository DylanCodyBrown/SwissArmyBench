# /// swissarmybench-widget
# format = 1
# name = "download_button"
# description = "Download a table as CSV"
# framework = "streamlit"
# group = "Buttons"
# tags = []
# size = [3, 1]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import In, Table, key, sample

# The table to download (empty: made-up sample data)
table_name: In[Table] = None
label = "Download CSV"
file_name = "table.csv"

frame = table_name if table_name is not None else sample()
st.download_button(
    label, frame.to_csv(index=False), file_name=file_name, mime="text/csv", key=key("download")
)
