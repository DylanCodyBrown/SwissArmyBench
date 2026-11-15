# /// swissarmybench-blade
# format = 1
# name = "Component clickable cards"
# kind = "snippet"
# description = "A card per value of a column with its total; a click sends the card back (two-way)"
# tags = ["streamlit", "component", "two-way", "filter"]
# family = "Components"
# language = "streamlit"
# cell_name = "<<label>> cards"
# ///
snippet = r"""
# Clickable cards: one card for each value of a column, with its total and its number of rows. Click
# a card to pick it (the page then shows only its rows); click it again to pick none (every row).
#
# Makes: <<name: picked_{column}>>, <<rows name: by_{column}>>
#   <<name>>: the value of <<column>> on the card picked (None while none is)
#   <<rows name>>: the rows of <<table>> for that card (every row while none is), for other pieces to read
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
# This piece uses 3, a v2 component: a click has to come back to Python, which only a two-way
# component can do. How the value travels:
#   Python to the page:  data={...} (plain text and numbers) reaches the JavaScript as `data`.
#   The page to Python:  setStateValue("picked", value) in the JavaScript reruns the page, and the
#                        mount call gives the value back: _result.picked.
# A state value (setStateValue) stays until the next click; a trigger (setTriggerValue) is there for
# one rerun only. A pick is a state: the cards remember it.
import streamlit as st

# One card for each value: its total and its rows, worked out here in Python. They are handed to the
# component as data (plain text and numbers), never pasted into its HTML or JavaScript.
_totals = <<table>>.groupby("<<column>>")["<<value column>>"].agg(["sum", "count"])
_cards = [
    {"label": str(_value), "total": f"{_row['sum']:,.0f}", "rows": f"{int(_row['count']):,} rows"}
    for _value, _row in _totals.iterrows()
]

_CARDS_HTML = '<div class="cards" role="listbox"></div>'
_CARDS_CSS = '''
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
.card { all: unset; box-sizing: border-box; cursor: pointer; padding: 12px 14px; border-radius: 10px;
        border: 1px solid color-mix(in srgb, var(--st-text-color) 18%, transparent);
        background: var(--st-secondary-background-color); color: var(--st-text-color); font-family: var(--st-font); }
.card:hover { border-color: var(--st-primary-color); }
.card:focus-visible { outline: 2px solid var(--st-primary-color); outline-offset: 2px; }
.card[aria-selected="true"] { border-color: var(--st-primary-color); box-shadow: inset 0 0 0 2px var(--st-primary-color); }
.label { font-size: 12px; letter-spacing: .04em; text-transform: uppercase; opacity: .75; }
.total { font-size: 24px; font-weight: 650; font-variant-numeric: tabular-nums; margin: 2px 0; }
.rows { font-size: 12px; opacity: .7; }
'''
_CARDS_JS = '''
export default function (component) {
  // data: what Python sent. setStateValue: sends a value back. parentElement: where the HTML is.
  const { data, parentElement, setStateValue } = component;
  const grid = parentElement.querySelector(".cards");
  // This function runs again each time Python sends new data, so the cards are drawn afresh.
  grid.replaceChildren();
  grid.setAttribute("aria-label", data.label);
  for (const card of data.cards) {
    const button = document.createElement("button");
    button.className = "card";
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", String(card.label === data.picked));
    for (const [kind, text] of [["label", card.label], ["total", card.total], ["rows", card.rows]]) {
      const line = document.createElement("div");
      line.className = kind;
      line.textContent = text;  // textContent: the value as text, never as markup
      button.append(line);
    }
    // The click: the card's value goes back to Python (or null, to pick none), and the page reruns.
    button.onclick = () => setStateValue("picked", card.label === data.picked ? null : card.label);
    grid.append(button);
  }
}
'''
# Registered once by its name; the same name on a rerun is the same component.
_cards_component = st.components.v2.component(
    "sab_clickable_cards", html=_CARDS_HTML, css=_CARDS_CSS, js=_CARDS_JS
)
# The pick so far, so the cards can show which one is picked. st.session_state survives the reruns;
# the component keeps its state there under its key.
_before = st.session_state["<<name>>_pick"] if "<<name>>_pick" in st.session_state else {}
# key= gives the component a name of its own on the page: two with the same data would otherwise be
# taken for one, and Streamlit would stop with a "duplicate widget" error. default= is the value
# before any click; on_picked_change= says "picked" is a state this component sends (it must be given,
# even as a function that does nothing).
_result = _cards_component(
    key="<<name>>_pick",
    data={"label": "<<label>>", "cards": _cards, "picked": _before.get("picked")},
    default={"picked": None},
    on_picked_change=lambda: None,
)
<<name>> = _result.picked
# A name that starts with _ is this piece's own: other pieces do not read it.
<<rows name>> = (
    <<table>> if <<name>> is None else <<table>>[<<table>>["<<column>>"].astype(str) == <<name>>]
)
"""
