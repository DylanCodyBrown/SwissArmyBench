# /// swissarmybench-widget
# format = 1
# name = "radio_choice"
# description = "One choice of a few, all shown"
# framework = "streamlit"
# group = "Inputs"
# tags = []
# size = [3, 2]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import In, Out, Table, choices, key

label = "View"
options = ["Month", "Quarter", "Year"]
across = True
# Take the choices from a table's column instead (its distinct values, sorted; not wired: options)
options_table: In[Table] = None
options_column = ""  # column of options_table
# The choice, for the widgets on the page that read it
choice: Out[str] = None

choice = st.radio(label, choices(options, options_table, options_column), horizontal=across, key=key("radio"))
