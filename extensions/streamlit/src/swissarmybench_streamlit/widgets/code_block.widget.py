# /// swissarmybench-widget
# format = 1
# name = "code_block"
# description = "Code, with its colours"
# framework = "streamlit"
# group = "Text"
# tags = []
# size = [6, 2]
# min_size = [2, 1]
# ///
import streamlit as st

code = "SELECT region, sum(revenue) FROM orders GROUP BY region"
language = "sql"  # choices: sql, python, json, text

st.code(code, language=language)
