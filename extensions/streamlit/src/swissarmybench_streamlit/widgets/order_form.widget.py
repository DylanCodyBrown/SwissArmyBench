# /// swissarmybench-widget
# format = 1
# name = "order_form"
# description = "Pick a product and an amount, then Add"
# framework = "streamlit"
# group = "Forms"
# tags = []
# size = [5, 3]
# min_size = [3, 2]
# ///
import streamlit as st
from sab_canvas import key

products = ["Alpha", "Beta", "Gamma"]
button = "Add to order"

with st.form(key("order")):
    product = st.selectbox("Product", products, key=key("product"))
    amount = st.number_input("Amount", 1, 1000, 1, key=key("amount"))
    added = st.form_submit_button(button)
if added:
    st.session_state.setdefault(key("lines"), []).append({"product": product, "amount": amount})
if st.session_state.get(key("lines")):
    st.dataframe(st.session_state[key("lines")], hide_index=True)
