# /// swissarmybench-blade
# format = 1
# name = "Component keyboard shortcuts"
# kind = "snippet"
# description = "Listens for a few keys on the page and sends the one pressed back to Python (two-way)"
# tags = ["streamlit", "component", "two-way", "keyboard"]
# family = "Components"
# language = "streamlit"
# cell_name = "Keyboard shortcuts"
# ///
snippet = r"""
# Keyboard shortcuts: listens for a few keys anywhere on the page (not while you type in a box) and
# sends the one pressed back to Python, which can then act on it: the next page, a reset, a refresh.
#
# Makes: <<name: pressed_key>>
#   the key just pressed, in lowercase ("n"), on the one rerun the press starts; None on every other
# Reads: nothing
#
# Streamlit functions:
#   st.components.v2.component(name, html, css, js)   your own HTML, CSS and JavaScript as a component
#   st.caption(text)        small, quiet text
#
# Three ways to put your own HTML and JavaScript on a Streamlit page:
#   1. st.html(body, unsafe_allow_javascript=True)  on the page itself. One way: Python to the page.
#   2. st.iframe(html)                              a frame, a little page of its own. One way.
#   3. st.components.v2.component(...)              on the page, and TWO-WAY: its JavaScript sends a
#                                                   value back, and Python reads it on the rerun.
# The HTML, CSS and JavaScript you give them are code: they run as written. So a value from your data
# (or anything typed) is never pasted into them as code. Text is escaped with html.escape, a frame's
# data goes in as JSON, and a component gets its data in data= and puts it on the page as text.
#
# This piece uses 3, a v2 component: the key has to come back to Python, and it must hear keys on
# the app's whole page (a frame hears only the keys pressed inside it). How it travels:
#   Python to the page:  data={...} reaches the JavaScript as `data` (here the keys to listen for).
#   The page to Python:  setTriggerValue("pressed", key) in the JavaScript reruns the page, and the
#                        mount call gives the value back: _result.pressed.
# A trigger (setTriggerValue) is there for the one rerun the press starts, then None again, so
# pressing the same key twice acts twice. A state (setStateValue) would stay "n" after the first.
import streamlit as st

# The keys to listen for, as letters (or names such as arrowright), with commas between.
_keys = [_k.strip().lower() for _k in "<<keys: n, p, r>>".split(",") if _k.strip()]

_KEYS_HTML = '<div class="hint"></div>'
_KEYS_CSS = '.hint { font-size: 12px; opacity: .65; font-family: var(--st-font); color: var(--st-text-color); }'
_KEYS_JS = '''
export default function (component) {
  // data: what Python sent. setTriggerValue: sends a value back. parentElement: where the HTML is.
  const { data, parentElement, setTriggerValue } = component;
  parentElement.querySelector(".hint").textContent = "Keyboard shortcuts: " + data.keys.join(", ");
  // This function runs again each time Python sends new data (each rerun). The listener from the
  // run before is taken off first, so one press is sent once, not once per rerun so far.
  if (parentElement.sabListener) document.removeEventListener("keydown", parentElement.sabListener);
  parentElement.sabListener = (event) => {
    const typing = event.target.closest && event.target.closest("input, textarea, select, [contenteditable]");
    const key = event.key.toLowerCase();
    if (typing || event.ctrlKey || event.altKey || event.metaKey || !data.keys.includes(key)) return;
    event.preventDefault();
    setTriggerValue("pressed", key);
  };
  document.addEventListener("keydown", parentElement.sabListener);
  // Given back: what Streamlit runs when the component leaves the page (the listener goes with it).
  return () => document.removeEventListener("keydown", parentElement.sabListener);
}
'''
# Registered once by its name; the same name on a rerun is the same component.
_keys_component = st.components.v2.component("sab_keyboard_shortcuts", html=_KEYS_HTML, css=_KEYS_CSS, js=_KEYS_JS)
# key= gives the component a name of its own on the page: two with the same data would otherwise be
# taken for one, and Streamlit would stop with a "duplicate widget" error. on_pressed_change= says
# "pressed" is a value this component sends (it must be given, even as a function that does nothing).
_result = _keys_component(key="<<name>>_keys", data={"keys": _keys}, on_pressed_change=lambda: None)
<<name>> = _result.pressed
# What to do with a key is yours: for example, "if <<name>> == "n":" moves to the next page.
if <<name>>:
    st.caption("You pressed " + <<name>> + ".")
"""
