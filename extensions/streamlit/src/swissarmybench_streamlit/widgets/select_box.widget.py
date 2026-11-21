# /// swissarmybench-widget
# format = 1
# name = "select_box"
# description = "Pick one of a list"
# framework = "streamlit"
# group = "Inputs"
# tags = []
# size = [3, 1]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import In, Out, Table, choices, key

label = "Region"
options = ["North", "South", "East", "West"]
# Take the choices from a table's column instead (its distinct values, sorted; not wired: options)
options_table: In[Table] = None
options_column = ""  # column of options_table
# The choice, for the widgets on the page that read it
region: Out[str] = None

region = st.selectbox(label, choices(options, options_table, options_column), key=key("select"))
