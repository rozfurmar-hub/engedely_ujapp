import streamlit as st
import io
import json
import pandas as pd
import zipfile
from pathlib import Path
from typing import Any, Tuple

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

from datakezelo import list_records, delete_record
from ujapp import HU as HUMAN_LABELS

# ========== Segédek / titkolvasás ==========

def _get_secret(name: str, default: str | None = None) -> str | None:
    if name in st.secrets:
        return str(st.secrets[name])
    import os
    return os.environ.get(name, default)


# ========== Jogosultság ==========

def _admin_password_ok() -> bool:
    required = _get_secret("APP_ADMIN_PASSWORD")
    if not required:
        return False
    if "admin_auth" not in st.session_state:
        st.session_state["admin_auth"] = False
    return st.session_state["admin_auth"]

def _login_box() -> None:
    st.sidebar.header("Admin bejelentkezés")
    pwd = st.sidebar.text_input("Jelszó", type="password")
    if st.sidebar.button("Belépés", use_container_width=True):
        if pwd and pwd == _get_secret("APP_ADMIN_PASSWORD"):
            st.session_state["admin_auth"] = True
            st.toast("Sikeres bejelentkezés.", icon="✅")
        else:
            st.session_state["admin_auth"] = False
            st.sidebar.error("Hibás jelszó.")

# ========== Rekordok betöltése + DataFrame létrehozása ==========

records = list_records()
df = pd.DataFrame(records)

st.dataframe(df)

   
# Letöltések
if st.button("📄 PDF export"):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)

    story = []

    for _, row in df.iterrows():
        table = []
        for key, label in HUMAN_LABELS.items():
            value = row.get(key, "")
            table.append([label, str(value)])

        t = Table(table, colWidths=[200, 300])
        t.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('ALIGN', (0,0), (1,-1), 'LEFT'),
        ]))

        story.append(t)

    doc.build(story)
    buffer.seek(0)

    st.download_button(
        label="PDF export",
        data=buffer.getvalue(),
        file_name="export.pdf",
        mime="application/pdf"
    )
    
