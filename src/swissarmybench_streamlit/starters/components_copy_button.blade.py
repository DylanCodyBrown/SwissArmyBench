# /// swissarmybench-blade
# format = 1
# name = "Component copy table button"
# kind = "snippet"
# description = "A button that copies a table to the clipboard, ready to paste into Excel (two-way)"
# tags = ["streamlit", "component", "two-way", "clipboard"]
# family = "Components"
# language = "streamlit"
# cell_name = "Copy <<table>>"
# ///
snippet = r"""
# Copy table button: one click puts a table's rows on the clipboard as tab-separated text, so they
# paste into Excel (or an email) as cells. A message then says how many rows were copied.
#
# Makes: nothing (it copies, and says so)
# Reads: <<table>>
#   a table: an open one, or the rows a filter left (it copies what is shown now)
#
# Streamlit functions:
#   st.components.v2.component(name, html, css, js)   your own HTML, CSS and JavaScript as a component
#   st.toast(text, icon)    a short message that pops up in the corner and goes by itself
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
# This piece uses 3, a v2 component: it runs on the app's page, where the browser lets a click write
# to the clipboard (a frame may be refused), and it tells Python when it has copied. How it travels:
#   Python to the page:  data={...} reaches the JavaScript as `data` (here the text to copy).
#   The page to Python:  setTriggerValue("copied", rows) in the JavaScript reruns the page, and the
#                        mount call gives the value back: _result.copied.
# A trigger (setTriggerValue) is there for the one rerun the click starts, then None again, so the
# message shows once per click. A state (setStateValue) would stay, and show it on every rerun.
import streamlit as st

_shown = <<table>>.head(<<rows: 1000>>)
# The text to copy, made here in Python: a line of headings, then a line per row, tabs between.
_text = _shown.to_csv(sep="\t", index=False)

_COPY_HTML = '<button type="button"></button>'
_COPY_CSS = '''
button { cursor: pointer; padding: 6px 14px; border-radius: 8px; font: inherit; font-family: var(--st-font);
         color: var(--st-text-color); background: var(--st-secondary-background-color);
         border: 1px solid color-mix(in srgb, var(--st-text-color) 22%, transparent); }
button:hover { border-color: var(--st-primary-color); color: var(--st-primary-color); }
'''
_COPY_JS = '''
export default function (component) {
  // data: what Python sent. setTriggerValue: sends a value back. parentElement: where the HTML is.
  const { data, parentElement, setTriggerValue } = component;
  const button = parentElement.querySelector("button");
  button.textContent = data.label;  // textContent: the words as text, never as markup
  button.onclick = async () => {
    try {
      await navigator.clipboard.writeText(data.text);
    } catch (error) {
      // An older browser, or a page that is neither https nor this computer: the old way.
      const box = document.createElement("textarea");
      box.value = data.text;
      parentElement.append(box);
      box.select();
      document.execCommand("copy");
      box.remove();
    }
    button.textContent = "Copied";
    setTimeout(() => (button.textContent = data.label), 1500);
    setTriggerValue("copied", data.rows);
  };
}
'''
# Registered once by its name; the same name on a rerun is the same component.
_copy_component = st.components.v2.component("sab_copy_table", html=_COPY_HTML, css=_COPY_CSS, js=_COPY_JS)
# key= gives the component a name of its own on the page: two with the same data would otherwise be
# taken for one, and Streamlit would stop with a "duplicate widget" error. on_copied_change= says
# "copied" is a value this component sends (it must be given, even as a function that does nothing).
_result = _copy_component(
    key="<<table>>_copy",
    data={"label": "<<label: Copy table>>", "text": _text, "rows": len(_shown)},
    width="content",
    on_copied_change=lambda: None,
)
if _result.copied:
    st.toast(f"Copied {_result.copied:,} rows: paste them into Excel.", icon="📋")
"""
