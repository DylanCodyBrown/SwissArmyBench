# /// swissarmybench-widget
# format = 1
# name = "colour_picker"
# description = "Pick a colour"
# framework = "streamlit"
# group = "Inputs"
# tags = []
# size = [3, 1]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import key

label = "Colour"
colour = "#1f77b4"

st.color_picker(label, colour, key=key("colour"))
