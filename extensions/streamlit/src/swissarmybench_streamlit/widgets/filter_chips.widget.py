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
from sab_canvas import key

label = "Products"
options = ["Alpha", "Beta", "Gamma"]
state_key = "picked"

st.pills(label, options, selection_mode="multi", key=state_key or key("pills"))
