import json
from pathlib import Path
import streamlit as st

BASE = Path(__file__).parent

@st.cache_data
def load_field_help(lang="hu"):
    file = BASE / "knowledge" / f"fields_{lang}.json"
    if not file.exists():
        return {}
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except:
        return {}


import streamlit as st

def show_field_help(field_name, lang="hu"):
    from field_help import load_field_help
    kb = load_field_help(lang)
    info = kb.get(field_name)

    if not info:
        # akkor is jelenjen meg apró ikon — üres popoverrel
        with st.popover("ℹ️", use_container_width=False):
            st.write("Nincs elérhető információ.")
        return

    with st.popover("ℹ️", use_container_width=False):
        st.markdown(f"### {info['label']}")
        st.write(info["help"])
