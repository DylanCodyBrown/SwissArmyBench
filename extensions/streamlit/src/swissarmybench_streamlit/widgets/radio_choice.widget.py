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
from sab_canvas import key

label = "View"
options = ["Month", "Quarter", "Year"]
across = True

st.radio(label, options, horizontal=across, key=key("radio"))
