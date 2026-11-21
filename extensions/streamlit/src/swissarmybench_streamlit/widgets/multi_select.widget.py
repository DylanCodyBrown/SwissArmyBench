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
from sab_canvas import key

label = "Products"
options = ["Alpha", "Beta", "Gamma"]
picked = ["Alpha"]
state_key = "products"

st.multiselect(label, options, default=[p for p in picked if p in options], key=state_key or key("multi"))
