# /// swissarmybench-widget
# format = 1
# name = "link_button"
# description = "A button that opens a web address"
# framework = "streamlit"
# group = "Buttons"
# tags = []
# size = [3, 1]
# min_size = [2, 1]
# ///
import streamlit as st

# The button's words
label = "Open the report"
# Where it goes
url = "https://example.com/report"
kind = "secondary"  # choices: primary, secondary, tertiary

st.link_button(label, url, type=kind)
