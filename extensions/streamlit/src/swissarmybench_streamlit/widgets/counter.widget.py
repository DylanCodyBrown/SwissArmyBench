# /// swissarmybench-widget
# format = 1
# name = "counter"
# description = "A number with + and - buttons"
# framework = "streamlit"
# group = "Buttons"
# tags = []
# size = [3, 1]
# min_size = [3, 1]
# ///
import streamlit as st
from sab_canvas import Out, key

label = "Count"
start = 0
step = 1  # 1..100
# The count, for the widgets on the page that read it
count: Out[int] = None

value = st.session_state.setdefault(key("value"), start)
left, middle, right = st.columns([1, 2, 1])
if left.button("-", key=key("minus")):
    st.session_state[key("value")] = value - step
if right.button("+", key=key("plus")):
    st.session_state[key("value")] = value + step
count = st.session_state[key("value")]
middle.metric(label, count)
