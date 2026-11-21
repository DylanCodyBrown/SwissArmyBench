# /// swissarmybench-widget
# format = 1
# name = "slider"
# description = "A value on a slider"
# framework = "streamlit"
# group = "Inputs"
# tags = []
# size = [4, 1]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import key

label = "Threshold"
value = 50  # 0..100
smallest = 0
largest = 100
state_key = "threshold"

st.slider(label, smallest, largest, value, key=state_key or key("slider"))
