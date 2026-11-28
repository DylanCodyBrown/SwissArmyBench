# /// swissarmybench-widget
# format = 1
# name = "feedback_form"
# description = "A short form with Submit"
# framework = "streamlit"
# group = "Forms"
# tags = []
# size = [5, 4]
# min_size = [3, 3]
# ///
import streamlit as st
from sab_canvas import key

title = "Tell us what you think"
button = "Submit"
thanks = "Thank you!"

with st.form(key("form")):
    st.markdown(f"**{title}**")
    st.text_input("Name", key=key("name"))
    st.slider("Score", 1, 5, 4, key=key("score"))
    st.text_area("Comments", key=key("comments"))
    sent = st.form_submit_button(button)
if sent:
    st.success(thanks)
