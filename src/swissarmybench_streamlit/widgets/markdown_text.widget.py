# /// swissarmybench-widget
# format = 1
# name = "markdown_text"
# description = "Text with Markdown"
# framework = "streamlit"
# group = "Text"
# tags = []
# size = [6, 2]
# min_size = [2, 1]
# ///
import streamlit as st

text = "Revenue grew **4.5%** on last month, led by the *North* region."

st.markdown(text)
