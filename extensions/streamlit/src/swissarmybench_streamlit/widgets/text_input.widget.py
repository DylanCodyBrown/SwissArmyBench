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
from sab_canvas import Out, key

label = "Name"
placeholder = "Type here"
# The text, for the widgets on the page that read it
name: Out[str] = None

name = st.text_input(label, placeholder=placeholder, key=key("text"))
