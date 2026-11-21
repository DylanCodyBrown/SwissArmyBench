# /// swissarmybench-widget
# format = 1
# name = "number_input"
# description = "A number box with a range"
# framework = "streamlit"
# group = "Inputs"
# tags = []
# size = [3, 1]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import key

label = "Quantity"
value = 10
smallest = 0
largest = 100
state_key = "quantity"

st.number_input(label, min_value=smallest, max_value=largest, value=value, key=state_key or key("number"))
