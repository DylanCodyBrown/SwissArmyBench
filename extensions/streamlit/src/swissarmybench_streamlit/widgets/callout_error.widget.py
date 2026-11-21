# /// swissarmybench-widget
# format = 1
# name = "callout_error"
# description = "A red note"
# framework = "streamlit"
# group = "Text"
# tags = []
# size = [6, 1]
# min_size = [2, 1]
# ///
import streamlit as st

text = "The forecast is past its due date."

st.error(text)
