# /// swissarmybench-widget
# format = 1
# name = "input_file"
# description = "Upload one file or several, by type and size"
# framework = "streamlit"
# group = "Inputs"
# pack = "User inputs"
# tags = []
# size = [4, 2]
# min_size = [2, 2]
# ///
import streamlit as st
from sab_canvas import key

# The words above the input
label = "Attach a file"
# Shown beside the label as a ?
help_text = ""
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The session state key the value is kept under (empty: this widget's own)
state_key = ""
# Said under the input while it is required and missing, or does not fit
validation_message = "Attach a file."
# The file types taken (empty: any)
types = ["csv", "xlsx", "pdf", "png", "jpg"]
# Several files at once
multiple = False
# The largest file in MB (0: Streamlit's own limit)
max_mb: int = 0  # 0..1000


def _label(text, needed):
    """The pack's one required marker: a red star after the label."""
    return f"{text} :red[\\*]" if needed else text


def _problem(message):
    """The pack's one error look, under the input."""
    st.markdown(f":red[{message}]")


_key = state_key or key("value")
value = st.file_uploader(
    _label(label, required),
    type=types or None,
    accept_multiple_files=multiple,
    key=_key,
    max_upload_size=max_mb or None,
    help=help_text or None,
    disabled=disabled,
)
files = value if isinstance(value, list) else ([value] if value is not None else [])
if files:
    st.caption(" · ".join(f"{f.name} ({f.size / 1024:,.0f} KB)" for f in files))
elif required:
    _problem(validation_message)
