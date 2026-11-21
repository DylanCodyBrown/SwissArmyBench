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
from sab_canvas import key

_WIDGET = "cs_reply_form"
# The session state key the queue keeps the picked ticket's id under
selected_key = "ticket"
reply_label = "Reply"
placeholder = "Write to the customer…"
statuses = ["Open", "Waiting on customer", "Resolved", "Closed"]
button = "Send reply"
# Said under the reply while it is empty
validation_message = "Write a reply before sending."
# The session state key the reply is handed to the page under ({"event": "save", ...})
save_event = "reply_saved"


def _save(payload):
    """The page's hand-off: {"event": "save", "widget": ..., "payload": ...} under save_event."""
    st.session_state[save_event] = {"event": "save", "widget": _WIDGET, "payload": payload}


ticket = st.session_state.get(selected_key, 9100)
st.markdown(f"**Reply to ticket #{ticket}**")
with st.form(key("form")):
    text = st.text_area(f"{reply_label} :red[\\*]", placeholder=placeholder, key=key("text"))
    status = st.selectbox("Set the status to", statuses, key=key("status"))
    sent = st.form_submit_button(button)
if sent:
    if not text.strip():
        st.markdown(f":red[{validation_message}]")
    else:
        _save({"ticket_id": ticket, "reply": text.strip(), "status": status})
        st.success(f"Reply to ticket #{ticket} handed to the page.")
