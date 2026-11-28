# /// swissarmybench-widget
# format = 1
# name = "filter_chips"
# description = "Pills to pick values; others read the key"
# framework = "streamlit"
# group = "Filters"
# tags = []
# size = [5, 1]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import In, Out, Table, choices, key

label = "Products"
options = ["Alpha", "Beta", "Gamma"]
# Take the choices from a table's column instead (its distinct values, sorted; not wired: options)
options_table: In[Table] = None
options_column = ""  # column of options_table
# The chips picked, for the widgets on the page that read them
picked: Out[list[str]] = None

picked = st.pills(
    label, choices(options, options_table, options_column), selection_mode="multi", key=key("pills")
)
