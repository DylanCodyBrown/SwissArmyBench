# /// swissarmybench-widget
# format = 1
# name = "toggle"
# description = "An on and off switch"
# framework = "streamlit"
# group = "Inputs"
# tags = []
# size = [3, 1]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import Out, key

label = "Show details"
on = False
# On or off, for the widgets on the page that read it
details: Out[bool] = None

details = st.toggle(label, value=on, key=key("toggle"))
