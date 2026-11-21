# /// swissarmybench-widget
# format = 1
# name = "input_chat"
# description = "A chat box with its messages"
# framework = "streamlit"
# group = "Inputs"
# pack = "User inputs"
# tags = []
# size = [5, 5]
# min_size = [3, 3]
# ///
import streamlit as st
from sab_canvas import Out, key, marked, problem

# The words above the input
label = "Chat"
# Shown beside the label as a ?
help_text = ""
# Shown in the box while it is empty
placeholder = "Ask a question"
# The first message shown
default = "Hello, how can we help?"
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The value, for the widgets on the page that read it
value: Out[str] = None
# Said under the input while it is required and missing, or does not fit
validation_message = "Write a message."
# The most characters (0: no limit)
max_chars: int = 0  # 0..100000
# The answer shown to each message (the page or an API can answer instead)
answer = "Thank you: someone will answer shortly."


_key = key("value")
history = st.session_state.setdefault(
    key("history"), [{"role": "assistant", "content": default}] if default else []
)
if label:
    st.markdown(f"**{marked(label, required)}**")
box = st.container(height=220)
for message in history:
    box.chat_message(message["role"]).write(message["content"])
said = st.chat_input(placeholder or None, key=_key, max_chars=max_chars or None, disabled=disabled)
if said:
    history.append({"role": "user", "content": said})
    history.append({"role": "assistant", "content": answer})
    st.rerun()
if required and len([m for m in history if m["role"] == "user"]) == 0:
    problem(validation_message)
value = next((m["content"] for m in reversed(history) if m["role"] == "user"), None)
