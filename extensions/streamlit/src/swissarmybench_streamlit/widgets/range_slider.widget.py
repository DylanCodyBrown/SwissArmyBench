# /// swissarmybench-widget
# format = 1
# name = "range_slider"
# description = "A low and a high value"
# framework = "streamlit"
# group = "Inputs"
# tags = []
# size = [4, 1]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import key

label = "Price range"
low = 20  # 0..100
high = 80  # 0..100

st.slider(label, 0, 100, (min(low, high), max(low, high)), key=key("range"))
