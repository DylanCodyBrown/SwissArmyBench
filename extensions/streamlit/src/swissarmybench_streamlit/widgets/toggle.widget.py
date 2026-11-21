# /// swissarmybench-widget
# format = 1
# name = "toggle"
# description = "An on and off switch"
# framework = "streamlit"
# group = "Inputs"
# tags = []
# size = [3, 1]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import key

label = "Show details"
on = False
state_key = "details"

st.toggle(label, value=on, key=state_key or key("toggle"))
