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

def show_field_help(field_name, lang="hu"):
    kb = load_field_help(lang)
    info = kb.get(field_name)
    if info:
        st.info(f"**{info['label']}**\n\n{info['help']}")
