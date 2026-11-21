# /// swissarmybench-widget
# format = 1
# name = "input_audio"
# description = "Record a voice message"
# framework = "streamlit"
# group = "Inputs"
# pack = "User inputs"
# tags = []
# size = [4, 2]
# min_size = [2, 1]
# ///
import streamlit as st
from sab_canvas import key

# The words above the input
label = "Record a message"
# Shown beside the label as a ?
help_text = ""
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# The session state key the value is kept under (empty: this widget's own)
state_key = ""
# Said under the input while it is required and missing, or does not fit
validation_message = "Record a message."
# Samples a second (16000 for speech; 0: the browser's own)
sample_rate: int = 16000  # 0..48000


def _label(text, needed):
    """The pack's one required marker: a red star after the label."""
    return f"{text} :red[\\*]" if needed else text


def _problem(message):
    """The pack's one error look, under the input."""
    st.markdown(f":red[{message}]")


_key = state_key or key("value")
if not hasattr(st, "audio_input"):
    st.warning("This Streamlit has no audio input: it came in Streamlit 1.40.")
else:
    value = st.audio_input(
        _label(label, required),
        key=_key,
        sample_rate=sample_rate or None,
        help=help_text or None,
        disabled=disabled,
    )
    if value is not None:
        st.audio(value)
    elif required:
        _problem(validation_message)
