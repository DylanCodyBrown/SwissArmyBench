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
from sab_canvas import Out, key

label = "Quantity"
value = 10
smallest = 0
largest = 100
# The number, for the widgets on the page that read it
quantity: Out[float] = None

quantity = st.number_input(label, min_value=smallest, max_value=largest, value=value, key=key("number"))
