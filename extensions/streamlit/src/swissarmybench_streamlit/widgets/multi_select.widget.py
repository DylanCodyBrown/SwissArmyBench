# /// swissarmybench-widget
# format = 1
# name = "multi_select"
# description = "Pick several of a list"
# framework = "streamlit"
# group = "Inputs"
# tags = []
# size = [4, 1]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import In, Out, Table, choices, key

label = "Products"
options = ["Alpha", "Beta", "Gamma"]
picked = ["Alpha"]
# Take the choices from a table's column instead (its distinct values, sorted; not wired: options)
options_table: In[Table] = None
options_column = ""  # column of options_table
# The choices, for the widgets on the page that read them
products: Out[list[str]] = None

options = choices(options, options_table, options_column)
products = st.multiselect(label, options, default=[p for p in picked if p in options], key=key("multi"))
