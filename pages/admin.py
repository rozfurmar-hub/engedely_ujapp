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

# ========== Belépés ellenőrzése ==========
if not _admin_password_ok():
    _login_box()
    st.stop()

# ========== Rekordok betöltése + DataFrame létrehozása ==========

records = list_records()
df = pd.DataFrame(records)

st.dataframe(df)

# ========== Letöltött pdf-ben megjelenő mezők  ==========
PDF_FIELDS = {
    "vezeteknev": "Családi név (útlevél szerint)",
    "keresztnev": "Utónév (útlevél szerint)",
    "szuletesi_csaladi": "Születési családi név",
    "szuletesi_uto": "Születési utónév",
    "anyja_csaladi": "Anyja születési családi neve",
    "anyja_uto": "Anyja születési utóneve",
    "nem": "Nem",
    "allampolgarsag": "Állampolgárság",
    "nemzetiseg": "Nemzetiség",
    "csaladi_allapot": "Családi állapot",
    "szuletesi_datum": "Születési idő",
    "szuletesi_hely": "Születési hely",
    "szuletesi_orszag": "Születési ország",
    "vegzettseg": "Iskolai végzettség",
    "szakkepzettseg": "Szakképzettség",
    "magyarorszagra_erkezese_elotti_foglalkozas": "Érkezés előtti foglalkozás",
    "utlevel_szam": "Útlevélszám",
    "utlevel_kiadas": "Útlevél kiállításának dátuma",
    "utlevel_helye": "Kiállítás helye",
    "utlevel_tipus": "Útlevél típusa",
    "utlevel_lejarat": "Útlevél érvényessége",
    "helyrajzi_szam": "Helyrajzi szám",
    "iranyitoszam": "Irányítószám",
    "telepules": "Település",
    "kozterulet_nev": "Közterület neve",
    "kozterulet_jelleg": "Közterület jellege",
    "hazszam": "Házszám",
    "epulet": "Épület",
    "lepcsohaz": "Lépcsőház",
    "emelet": "Emelet",
    "ajto": "Ajtó",
    "szallas_jogcim": "Tartózkodás jogcíme",
    "elso_beutazas_helye": "Beutazás helye",
    "elso_beutazas_datuma": "Beutazás dátuma",
    "hossz_engedely_szam": "Hosszabbítás engedélyszáma",
    "hossz_engedely_ervenyes": "Engedély érvényessége",
    "atvetel_mod": "Átvétel módja",
    "postai_cim_tipus": "Postai cím típusa",
    "egeszseg_biztositas": "Egészségbiztosítás",
    "egeszseg_egyeb": "Biztosítás megjegyzése",
    "visszaut_orszag": "Visszautazás országa",
    "kozlekedesi_eszkoz": "Közlekedési eszköz",
    "van_utlevel": "Van útlevél?",
    "van_vizum": "Van vízum?",
    "van_menetjegy": "Van menetjegy?",
    "van_anyagi_fedezet": "Van anyagi fedezete?",
    "fedezet_osszeg": "Fedezet összege",
    "elozo_orszag": "Előző ország",
    "elozo_telepules": "Előző település",
    "elozo_cim": "Előző cím",
    "mas_schengen_okmany": "Más schengeni okmány?",
    "mas_schengen_tipus": "Okmány típusa",
    "mas_schengen_szam": "Okmány száma",
    "mas_schengen_ervenyes": "Okmány érvényessége",
    "volt_elutasitas": "Volt elutasítás?",
    "volt_buntetve": "Volt büntetve?",
    "buntet_reszletek": "Bűncselekmény részletei",
    "volt_kiutasitas": "Kiutasították?",
    "kiutasitas_datum": "Kiutasítás dátuma",
    "fert_beteg": "Fertőző betegségek",
    "kap_ellatas": "Ellátást kap?",
    "kiskoru_utazik": "Kiskorú utazik?",
    "tartozkodas_vege": "Tartózkodás vége",
    "tartozkodas_celja": "Tartózkodás célja",
    "tranzakcio_szam": "Tranzakciószám"
}

# ========== UNICODE FONT REGISZTRÁLÁSA (hosszú ő,ű megjelenítése miatt) ==========
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
pdfmetrics.registerFont(TTFont("NotoSans", "fonts/NotoSans-Regular.ttf"))


# Letöltések
if st.button("📄 PDF export"):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)

    story = []

    for _, row in df.iterrows():
        table = []
        for key, label in PDF_FIELDS.items():
            value = row.get(key, "")
            table.append([label, str(value)])

        t = Table(table, colWidths=[200, 300])
        t.setStyle(TableStyle([
            ('FONT', (0,0), (-1,-1), 'NotoSans', 10),
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
    
