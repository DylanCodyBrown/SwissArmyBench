# /// swissarmybench-widget
# format = 1
# name = "text_input"
# description = "A line of text the page can read"
# framework = "streamlit"
# group = "Inputs"
# tags = []
# size = [4, 1]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import key

label = "Name"
placeholder = "Type here"
# The session state key other widgets read
state_key = "name"

st.text_input(label, placeholder=placeholder, key=state_key or key("text"))
