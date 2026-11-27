# /// swissarmybench-widget
# format = 1
# name = "callout_success"
# description = "A green note"
# framework = "streamlit"
# group = "Text"
# tags = []
# size = [6, 1]
# min_size = [2, 1]
# ///
import streamlit as st

text = "Every order this month has shipped."

st.success(text)
