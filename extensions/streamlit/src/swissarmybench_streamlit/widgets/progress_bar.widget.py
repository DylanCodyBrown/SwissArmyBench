# /// swissarmybench-widget
# format = 1
# name = "progress_bar"
# description = "How far along something is"
# framework = "streamlit"
# group = "Data"
# tags = []
# size = [4, 1]
# min_size = [2, 1]
# ///
import streamlit as st

label = "Target reached"
percent = 64  # 0..100

st.progress(percent / 100, text=f"{label}: {percent}%")
