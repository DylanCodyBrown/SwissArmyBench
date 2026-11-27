# /// swissarmybench-widget
# format = 1
# name = "text_area"
# description = "Several lines of text"
# framework = "streamlit"
# group = "Inputs"
# tags = []
# size = [4, 2]
# min_size = [2, 2]
# ///
import streamlit as st
from sab_canvas import key

label = "Notes"
height = 120  # 68..600

st.text_area(label, height=height, key=key("area"))
