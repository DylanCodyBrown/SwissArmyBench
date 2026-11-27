# /// swissarmybench-widget
# format = 1
# name = "title"
# description = "A page's title"
# framework = "streamlit"
# group = "Text"
# tags = []
# size = [8, 1]
# min_size = [2, 1]
# ///
import streamlit as st

text = "Sales overview"
level = "title"  # choices: title, header, subheader

getattr(st, level)(text)
