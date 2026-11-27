# /// swissarmybench-widget
# format = 1
# name = "checkbox"
# description = "A tick box"
# framework = "streamlit"
# group = "Inputs"
# tags = []
# size = [3, 1]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import key

label = "I agree"
ticked = False

st.checkbox(label, value=ticked, key=key("check"))
