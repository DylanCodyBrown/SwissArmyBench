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
from sab_canvas import key

label = "Region"
options = ["North", "South", "East", "West"]
state_key = "region"

st.selectbox(label, options, key=state_key or key("select"))
