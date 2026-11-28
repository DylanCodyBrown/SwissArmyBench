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
from sab_canvas import File, Out, as_file, key, marked, problem

# The words above the input
label = "Record a message"
# Shown beside the label as a ?
help_text = ""
# The viewer must give a value (a red star; the message below while it is missing)
required = False
disabled = False
# Said under the input while it is required and missing, or does not fit
validation_message = "Record a message."
# Samples a second (16000 for speech; 0: the browser's own)
sample_rate: int = 16000  # 0..48000
# The recording (a WAV file: its name, size, type and bytes), for the page's widgets
file: Out[File] = None


_key = key("value")
if not hasattr(st, "audio_input"):
    st.warning("This Streamlit has no audio input: it came in Streamlit 1.40.")
else:
    value = st.audio_input(
        marked(label, required),
        key=_key,
        sample_rate=sample_rate or None,
        help=help_text or None,
        disabled=disabled,
    )
    file = as_file(value)
    if value is not None:
        st.audio(value)
    elif required:
        problem(validation_message)
