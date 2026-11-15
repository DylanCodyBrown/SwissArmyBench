# /// swissarmybench-blade
# format = 1
# name = "Page callout"
# kind = "snippet"
# description = "A coloured box with a title and a message: a note the reader should see"
# tags = ["streamlit", "text", "layout"]
# family = "Text and layout"
# language = "streamlit"
# cell_name = "<<title: Note>> callout"
# ///
snippet = r"""
# Callout: a coloured box with a title and a message, for a note the reader should not miss.
#
# Makes: nothing (it only shows)
# Reads: nothing
#
# Streamlit functions:
#   st.info(text, icon)   a blue box; st.success is green, st.warning yellow, st.error red
#
# The text is Markdown: **bold** works, and two spaces then a new line start a new line. The icon
# is one of Google's Material Symbols, named as :material/<name>: (here "info").
import streamlit as st

st.info(
    "**<<title: Note>>**  \n<<message: The month closes on the 5th; until then the figures can change.>>",
    icon=":material/info:",
)
"""
