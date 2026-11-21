# /// swissarmybench-widget
# format = 1
# name = "caption_text"
# description = "A small line of text"
# framework = "streamlit"
# group = "Text"
# tags = []
# size = [4, 1]
# min_size = [1, 1]
# ///
import streamlit as st

text = "Figures in euros, made-up data."

st.caption(text)
