# /// swissarmybench-widget
# format = 1
# name = "callout_warning"
# description = "An amber warning"
# framework = "streamlit"
# group = "Text"
# tags = []
# size = [6, 1]
# min_size = [2, 1]
# ///
import streamlit as st

text = "Three regions have not reported yet."

st.warning(text)
