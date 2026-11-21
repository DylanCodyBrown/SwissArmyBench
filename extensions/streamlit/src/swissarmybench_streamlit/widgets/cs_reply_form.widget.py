# /// swissarmybench-widget
# format = 1
# name = "cs_reply_form"
# description = "Reply to the picked ticket and set its status; Send hands it to the page"
# framework = "streamlit"
# group = "Forms"
# pack = "Customer service"
# tags = []
# size = [5, 4]
# min_size = [3, 3]
# ///
import streamlit as st
from sab_canvas import Event, In, key

# The ticket replied to: the queue's picked ticket_id, wired by itself (none: 9100)
ticket_id: In[int] = None
reply_label = "Reply"
placeholder = "Write to the customer…"
statuses = ["Open", "Waiting on customer", "Resolved", "Closed"]
button = "Send reply"
# Said under the reply while it is empty
validation_message = "Write a reply before sending."
# Fired on Send: the reply (ticket_id, reply, status); the Canvas wires what it does (call an API.py endpoint, set a page value, rerun)
sent: Event[dict] = None


ticket = ticket_id if ticket_id is not None else 9100
st.markdown(f"**Reply to ticket #{ticket}**")
with st.form(key("form")):
    text = st.text_area(f"{reply_label} :red[\\*]", placeholder=placeholder, key=key("text"))
    status = st.selectbox("Set the status to", statuses, key=key("status"))
    sent = st.form_submit_button(button)
if sent:
    if not text.strip():
        st.markdown(f":red[{validation_message}]")
    else:
        sent({"ticket_id": ticket, "reply": text.strip(), "status": status})
        st.success(f"Reply to ticket #{ticket} handed to the page.")
