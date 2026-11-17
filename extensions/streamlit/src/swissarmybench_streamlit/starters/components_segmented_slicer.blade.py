# /// swissarmybench-blade
# format = 1
# name = "Component segmented slicer"
# kind = "snippet"
# description = "A row of buttons, one per value of a column; the one clicked is sent back (two-way)"
# tags = ["streamlit", "component", "two-way", "filter"]
# family = "Components"
# language = "streamlit"
# cell_name = "<<label>> slicer"
# ///
snippet = r"""
# Segmented slicer: a row of joined buttons, "All" and one for each value of a column, like a Power BI
# slicer. The one clicked is lit, and only its rows go on.
# (Streamlit has its own st.segmented_control; this one shows how to build a control of your own look.)
#
# Makes: <<name: picked_{column}>>, <<rows name: by_{column}>>
#   <<name>>: the value of <<column>> clicked ("All" before any click)
#   <<rows name>>: the rows of <<table>> for it ("All": every row), for other pieces to read
# Reads: <<table>>
#   a table: an open one, or the rows another filter left
#
# Streamlit functions:
#   st.components.v2.component(name, html, css, js)   your own HTML, CSS and JavaScript as a component
#   st.session_state        a dictionary Streamlit keeps for each person's open page between reruns
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
# This piece uses 3, a v2 component: the button clicked has to come back to Python. How it travels:
#   Python to the page:  data={...} reaches the JavaScript as `data` (here the buttons' words).
#   The page to Python:  setStateValue("picked", value) in the JavaScript reruns the page, and the
#                        mount call gives the value back: _result.picked.
# A state value (setStateValue) stays until the next click; a trigger (setTriggerValue) is there for
# one rerun only. A slicer's pick is a state.
import streamlit as st

# The buttons' words: "All", then each value of the column once, in order, as text (data, not code).
_options = ["All", *sorted(str(_v) for _v in <<table>>["<<column>>"].dropna().unique())]

_SLICER_HTML = '<div class="slicer" role="radiogroup"></div>'
_SLICER_CSS = '''
.slicer { display: inline-flex; flex-wrap: wrap; border: 1px solid color-mix(in srgb, var(--st-text-color) 22%, transparent);
          border-radius: 8px; overflow: hidden; font-family: var(--st-font); }
button { all: unset; cursor: pointer; padding: 6px 14px; font-size: 14px; color: var(--st-text-color);
         border-right: 1px solid color-mix(in srgb, var(--st-text-color) 15%, transparent); }
button:last-child { border-right: 0; }
button:hover { background: var(--st-secondary-background-color); }
button:focus-visible { outline: 2px solid var(--st-primary-color); outline-offset: -2px; }
button[aria-checked="true"] { background: var(--st-primary-color); color: #fff; }
'''
_SLICER_JS = '''
export default function (component) {
  // data: what Python sent. setStateValue: sends a value back. parentElement: where the HTML is.
  const { data, parentElement, setStateValue } = component;
  const row = parentElement.querySelector(".slicer");
  row.setAttribute("aria-label", data.label);
  // This function runs again each time Python sends new data, so the buttons are drawn afresh.
  row.replaceChildren();
  for (const option of data.options) {
    const button = document.createElement("button");
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", String(option === data.picked));
    button.textContent = option;  // textContent: the value as text, never as markup
    // The click: the value goes back to Python and the page reruns.
    button.onclick = () => setStateValue("picked", option);
    row.append(button);
  }
}
'''
# Registered once by its name; the same name on a rerun is the same component.
_slicer_component = st.components.v2.component(
    "sab_segmented_slicer", html=_SLICER_HTML, css=_SLICER_CSS, js=_SLICER_JS
)
# The pick so far, so the slicer can light it. st.session_state survives the reruns; the component
# keeps its state there under its key.
_before = st.session_state["<<name>>_pick"] if "<<name>>_pick" in st.session_state else {}
# key= gives the component a name of its own on the page: two with the same data would otherwise be
# taken for one, and Streamlit would stop with a "duplicate widget" error. default= is the value
# before any click; on_picked_change= says "picked" is a state this component sends (it must be given,
# even as a function that does nothing).
_result = _slicer_component(
    key="<<name>>_pick",
    data={"label": "<<label>>", "options": _options, "picked": _before.get("picked", "All")},
    default={"picked": "All"},
    on_picked_change=lambda: None,
)
<<name>> = _result.picked if _result.picked in _options else "All"
# A name that starts with _ is this piece's own: other pieces do not read it.
<<rows name>> = (
    <<table>> if <<name>> == "All" else <<table>>[<<table>>["<<column>>"].astype(str) == <<name>>]
)
"""
