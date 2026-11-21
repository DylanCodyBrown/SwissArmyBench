# /// swissarmybench-widget
# format = 1
# name = "json_view"
# description = "A value shown as a tree"
# framework = "streamlit"
# group = "Data"
# tags = []
# size = [4, 3]
# min_size = [2, 2]
# ///
import streamlit as st

value = {"customer": "Contoso", "orders": [{"id": 1, "total": 120.5}, {"id": 2, "total": 88.0}]}
expanded = True

st.json(value, expanded=expanded)
