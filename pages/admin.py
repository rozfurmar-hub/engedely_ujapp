import streamlit as st
import io
import json
import pandas as pd
from pathlib import Path
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from datakezelo import list_records
# ---------------------------------------------------

pdfmetrics.registerFont(TTFont("NotoSans", "fonts/NotoSans-Regular.ttf"))

# ---------------------------------------------------
# Admin jelszókezelés
# ---------------------------------------------------

def _get_secret(name, default=None):
    if name in st.secrets:
        return st.secrets[name]
    import os
    return os.environ.get(name, default)

def _admin_password_ok():
    required = _get_secret("APP_ADMIN_PASSWORD")
    if not required:
        return False
    return st.session_state.get("admin_auth", False)

def _login_box():
    st.sidebar.header("Admin bejelentkezés")
    pwd = st.sidebar.text_input("Jelszó", type="password")
    if st.sidebar.button("Belépés"):
        if pwd == _get_secret("APP_ADMIN_PASSWORD"):
            st.session_state["admin_auth"] = True
            st.success("Sikeres belépés.")
        else:
            st.session_state["admin_auth"] = False
            st.error("Hibás jelszó.")

# ---------------------------------------------------
# Beléptetés
# ---------------------------------------------------
if not _admin_password_ok():
    _login_box()
    st.stop()

# ---------------------------------------------------
# Rekordok listázása
# ---------------------------------------------------

records = list_records()
df = pd.DataFrame(records)

st.title("📁 Admin felület – összes rekord")
st.dataframe(df, use_container_width=True)

# ---------------------------------------------------
# PDF-ben megjelenő mezők
# ---------------------------------------------------

PDF_FIELDS = {
    "vezeteknev": "Családi név",
    "keresztnev": "Utónév",
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
    "vegzettseg": "Végzettség",
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
    "szallas_jogcim": "Szállás jogcíme",
    "elso_beutazas_helye": "Beutazás helye",
    "elso_beutazas_datuma": "Beutazás dátuma",
    "hossz_engedely_szam": "Engedély száma",
    "hossz_engedely_ervenyes": "Engedély érvényessége",
    "atvetel_mod": "Átvétel módja",
    "postai_cim_tipus": "Postai cím típusa",
    "egeszseg_biztositas": "Egészségbiztosítás",
    "egeszseg_egyeb": "Egészségbiztosítás megjegyzés",
    "visszaut_orszag": "Visszautazás országa",
    "kozlekedesi_eszkoz": "Közlekedési eszköz",
    "van_utlevel": "Van útlevele?",
    "van_vizum": "Van vízuma?",
    "van_menetjegy": "Van menetjegye?",
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
    "volt_kiutasitas": "Volt kiutasítás?",
    "kiutasitas_datum": "Kiutasítás dátuma",
    "fert_beteg": "Fertőző betegség?",
    "kap_ellatas": "Kap ellátást?",
    "kiskoru_utazik": "Kiskorú utazik?",
    "tartozkodas_vege": "Tartózkodás vége",
    "tartozkodas_celja": "Tartózkodás célja",
    "tranzakcio_szam": "Tranzakciószám",
}

# ---------------------------------------------------
# PDF KÉSZÍTÉSE
# ---------------------------------------------------

st.subheader("📄 PDF export")

with st.form("pdf_export_form"):
    generate_pdf = st.form_submit_button("PDF készítése")

if generate_pdf:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    story = []
    styles = getSampleStyleSheet()

    for _, row in df.iterrows():

        # --- FŐ MEZŐK ---
        table_data = []
        for key, label in PDF_FIELDS.items():
            value = row.get(key, "")
            table_data.append([label, str(value)])

        table = Table(table_data, colWidths=[200, 300])
        table.setStyle(TableStyle([
            ('FONT', (0,0), (-1,-1), 'NotoSans', 9),
            ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        story.append(table)
        story.append(Spacer(1, 10))

        # --- HOZZÁTARTOZÓK ---
        hozz_json = row.get("hozzatartozok_json", "[]")

        try:
            hozz = json.loads(hozz_json)
        except:
            hozz = []

        if hozz:
            story.append(Paragraph("<b>Hozzátartozók:</b>", styles["Normal"]))

            for idx, h in enumerate(hozz, start=1):
                txt = (
                    f"{idx}. hozzátartozó\n"
                    f"Vezetéknév: {h.get('vezeteknev','')}\n"
                    f"Keresztnév: {h.get('keresztnev','')}\n"
                    f"Rokonsági fok: {h.get('rokonsagi_fok','')}\n"
                    f"Születési hely: {h.get('szuletesi_hely','')}\n"
                    f"Születési idő: {h.get('szuletesi_ido','')}\n"
                    f"Anyja neve: {h.get('anyja_vezetek','')} {h.get('anyja_kereszt','')}\n"
                    f"Állampolgárság: {h.get('allampolgarsag','')}\n"
                    f"Magyarországon tartózkodik-e: {h.get('tartozkodik_e','')}\n"
                    f"Okmányszám: {h.get('okmany_szam','')}\n"
                )
                
                story.append(Paragraph(txt.replace("\n", "<br/>"), styles["Normal"]))
                story.append(Spacer(1, 8))


    # --- PDF mentése ---
    doc.build(story)
    buffer.seek(0)

    st.download_button(
        label="📥 PDF letöltése",
        data=buffer.getvalue(),
        file_name="export.pdf",
        mime="application/pdf"
    )
