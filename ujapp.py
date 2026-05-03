# ujapp.py — Adatbekérő űrlap a „Tartózkodási engedély iránti kérelem” és a „Szálláshely bejelentése” nyomtatványokhoz
# HU/RU i18n + RU latin-írás figyelmeztetés + automatikus transzliteráció + (néhány mező RU->HU fordítás)
# Docx sablonok: a későbbiekben készülnek el, de a helyőrzők listája és a context már ebben az appban rögzített.
# A meglévő app.py fő funkcióit megőrzi: sablonválasztás, upsert, ZIP, validáció, transliteráció — egyszerűsítve.

import io
import os
import re
import json
import unicodedata
import zipfile
import requests
from pathlib import Path
from datetime import datetime, date
from dateutil.parser import parse as parse_date

import streamlit as st
from docxtpl import DocxTemplate

from chat_widget import floating_chat
from field_help import show_field_help

def render_text_field(key, label, ui_lang, placeholder=""):
    col1, col2 = st.columns([10, 1])
    with col1:
        st.markdown(f"{label}")
    with col2:
        show_field_help(key, ui_lang)
    return st.text_input("", key=key, placeholder=placeholder)

def render_select_field(key, label, options, ui_lang, index=0):
    col1, col2 = st.columns([10, 1])
    with col1:
        st.markdown(f"{label}")
    with col2:
        show_field_help(key, ui_lang)
    return st.selectbox("", options=options, index=index, key=key)

def translit(v: str) -> str:
    return transliterate_to_latin(v) if contains_cyrillic(v) else v

# ====== Segédfüggvény: fordítás cirill esetén, fallback translit ======
def translate_or_translit(v: str) -> str:
    if not v:
        return ""
    if contains_cyrillic(v):
        hu = translator_translate_to_hungarian(v)
        return hu or transliterate_to_latin(v)
    return v

# ---- Adatkezelő modul (meglévő környezetből) ----
from datakezelo import BASE_DIR, create_record, list_records, update_record

# ---- Oldal beállítás ----
st.set_page_config(page_title="Tartózkodási engedély – adatbekérő", page_icon="📝", layout="centered")

# 🔥 FONTOS: A chat KÜLÖN, önálló blokkban fusson, NEM with alatt
floating_chat()

# ---- Itt kell lennie a CSS-nek ----
st.markdown("""
<style>
/* Rejtsük el a Streamlit alap chat-ablakát */
[data-testid="stChat"] {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)



DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"

# A két cél-nyomtatványhoz várható sablonfájl-nevek (később kerülnek elkészítésre)
DEFAULT_TEMPLATE_NAMES = [
    "Tartozkodasi_engedely_kerelem_sablon.docx",
    "Szallashely_bejelentese_sablon.docx",
]

# =========================
# I18n (HU + RU)
# =========================

def load_labels(lang: str) -> dict:
    """Külső i18n JSON felülírhatja a beépített feliratokat (ha létezik)."""
    # 1) beépített alap (a jelenlegi HU/RU dict-ek felépítése marad)
    base = (load_labels.__dict__['_RU'] if lang=='ru' else load_labels.__dict__['_HU']) if ('_HU' in load_labels.__dict__ and '_RU' in load_labels.__dict__) else None
    if base is None:
        base = {}
    # 2) próbáljuk meg beolvasni a külső JSON-t (BASE_DIR/i18n/strings_{lang}.json)
    try:
        i18n_dir = (BASE_DIR / 'i18n')
    except Exception:
        i18n_dir = Path('i18n')
    pjson = i18n_dir / f'strings_{lang}.json'
    if pjson.exists():
        try:
            external = json.loads(pjson.read_text(encoding='utf-8'))
            merged = dict(base) if isinstance(base, dict) else {}
            merged.update(external or {})
            return merged
        except Exception:
            pass
    return base if isinstance(base, dict) else {}

# Beépített HU/RU szótárak (fallback)
HU = {
    "app_title": "📝 Tartózkodási engedély – adatbekérő (HU/RU)",
    "app_caption": "Adatai alapján néhány dokumentum készül, amit kérünk lementeni és megküldeni Nagy Máriának a maria.nagy@hungaria-xxx.com e-mail címre.",
    "sidebar_hdr_templates": "Elérhető sablonok",
    "help_header": "ℹ️ Használati útmutató",
    "help_md": (
        "1) Töltse ki az űrlapot magyarul vagy oroszul. Orosz UI esetén kérjük latin betűkkel írni.\n"
        "2) Válassza ki, hogy melyik dokumentum sablon készüljön.\n"
        "3) A 'Generálás' gomb megnyomására a kiválasztott DOCX sablon(ok) elkészülnek és letölthetők."
    ),
    "sidebar_lang": "Nyelv / Язык",
    "ru_latin_notice": "⚠️ Orosz nyelvű felület esetén kérjük *latin* betűkkel (A–Z, 0–9) kitölteni. A cirill szövegeket automatikusan latinra írjuk át, kivéve néhány mezőt, amelyeket magyarra fordítunk.",
    "form_header": "Adatbekérő űrlap",
    "btn_generate": "📄 Dokumentum(ok) generálása",
    "select_templates": "12) Válasszon sablon(oka)t a lenyíló menüből",
    "err_no_templates": "Nincs sablon a templates/ mappában.",
    "err_no_selection": "Nem választott ki sablont.",
    "err_fix": "Kérjük, javítsa az alábbi hibá(ka)t:",
    "err_required_name": "A családi és utónév megadása kötelező.",
    "err_invalid_date": "Érvénytelen dátum: {field}",
    "err_past_date": "A(z) {field} nem lehet múltbeli.",
    "err_bad_passport": "Útlevélszám formátum hibás.",
    "succ_upsert": "{msg}. {n} dokumentum elkészült.",
    "succ_new": "Új rekord LÉTREHOZVA (ID: {id}) – {nev}",
    "succ_update": "Rekord FRISSÍTVE (ID: {id}) – {nev}",
    "btn_download_doc": "⬇️ Letöltés: {fname}",
    "btn_download_zip": "📦 Összes dokumentum ZIP-ben",
    "table_header": "Felvitt rekordok (utolsó 20)",
    "table_col_id": "ID",
    "table_col_nev": "név",
    "table_col_dob": "szül. dátum",
    "table_col_pass": "útlevél",
    "table_col_perm": "engedély",
    "info_no_records": "Még nincs felvitt rekord.",

    # Mezőcímkék
    "section_contact": "Elérhetőség",
    "phone": "Telefonszám",
    "email": "E-mail cím",
    "section_personal": "1) Személyes adatok",
    "vezeteknev": "Családi név (útlevél szerint)",
    "keresztnev": "Utónév (útlevél szerint)",
    "szuletesi_csaladi": "Születési családi név",
    "szuletesi_uto": "Születési utónév",
    "anyja_csaladi": "Anyja születési családi neve",
    "anyja_uto": "Anyja születési utóneve",
    "nem": "Nem",
    "allampolgarsag": "Állampolgárság",
    "nemzetiseg": "Nemzetiség (nem kötelező)",
    "csaladi_allapot": "Családi állapot",
    "szuletesi_datum": "Születési idő (YYYY-MM-DD)",
    "szuletesi_hely": "Születési hely (település)",
    "szuletesi_orszag": "Születési ország",
    "vegzettseg": "Iskolai végzettség",
    "szakkepzettseg": "Szakképzettség (RU→HU fordítás)",
    "elozo_foglalkozas": "Magyarországra érkezést megelőző foglalkozás (RU→HU fordítás)",

    "section_passport": "2) Útlevél adatok",
    "utlevel_szam": "Útlevél száma",
    "utlevel_kiadas": "Útlevél kiállításának dátuma (YYYY-MM-DD)",
    "utlevel_helye": "Kiállítás helye",
    "utlevel_tipus": "Útlevél típusa",
    "utlevel_lejarat": "Útlevél érvényessége (YYYY-MM-DD)",

    "section_szallas": "3) Magyarországi szálláshely",
    "helyrajzi_szam": "Helyrajzi szám (nem kötelező)",
    "iranyitoszam": "Irányítószám",
    "telepules": "Település",
    "kozterulet_nev": "Közterület neve",
    "kozterulet_jelleg": "Közterület jellege",
    "hazszam": "Házszám",
    "epulet": "Épület",
    "lepcsohaz": "Lépcsőház",
    "emelet": "Emelet",
    "ajto": "Ajtó",
    "szallas_jogcim": "A szálláshelyen tartózkodás jogcíme",

    "section_elso_vagy_hossz": "4) Első kérelem / Hosszabbítás",
    "elso_beutazas_helye": "Első kérelemnél: beutazás helye",
    "elso_beutazas_datuma": "Első kérelemnél: beutazás ideje (YYYY-MM-DD)",
    "hossz_engedely_szam": "Hosszabbításnál: engedély száma",
    "hossz_engedely_ervenyes": "Hosszabbításnál: engedély érvényessége (YYYY-MM-DD)",

    "section_atvetel": "5) Okmány átvétele",
    "atvetel_mod": "Átvétel módja",
    "postai_cim_tipus": "Postai kézbesítés címe",

    "section_egeszseg": "6) Teljes körű egészségbiztosítás",
    "egeszseg_biztositas": "Rendelkezik teljes körű egészségbiztosítással?",
    "egeszseg_egyeb": "Egyéb (biztosítás típusa, megjegyzés)",

    "section_visszaut": "7) Vissza-/továbbutazás feltételei",
    "visszaut_orszag": "Vissza-/továbbutazás országa",
    "kozlekedesi_eszkoz": "Közlekedési eszköz",
    "van_utlevel": "Rendelkezik útlevéllel?",
    "van_vizum": "Rendelkezik vízummal?",
    "van_menetjegy": "Rendelkezik menetjeggyel?",
    "van_anyagi_fedezet": "Rendelkezik anyagi fedezettel?",
    "fedezet_osszeg": "Anyagi fedezet összege",

    "section_hozzatartozo": "Eltartott házastárs/gyermek/szülő (max. 8 fő)",
    "hozz_count": "Eltartott hozzátartozók száma",

    "section_egyeb": "8) Egyéb adatok",
    "elozo_orszag": "(Érkezés előtti) Ország",
    "elozo_telepules": "(Érkezés előtti) Település",
    "elozo_cim": "(Érkezés előtti) Cím",
    "mas_schengen_okmany": "Más schengeni tartózkodási okmánya van?",
    "mas_schengen_tipus": "Engedély típusa",
    "mas_schengen_szam": "Engedély száma",
    "mas_schengen_ervenyes": "Érvényesség (YYYY-MM-DD)",
    "volt_elutasitas": "Volt-e korábban elutasított kérelem?",
    "volt_buntetve": "Volt-e korábban büntetve?",
    "buntet_reszletek": "Bűncselekmény részletei (ország, mikor, miért, büntetés)",
    "volt_kiutasitas": "Kiutasították-e korábban Magyarországról?",
    "kiutasitas_datum": "Kiutasítás dátuma (YYYY-MM-DD)",
    "fert_beteg": "Szenved-e a felsorolt fertőző betegségek valamelyikében? Tudomása szerint szenved-e gyógykezelésre szoruló HIV/AIDS, továbbá tbc, hepatitis B, luesz, lepra, hastífusz fertőző betegségekben?",
    "kap_ellatas": "Fertőzőképesség esetén részesül-e kötelező és rendszeres ellátásban?",

    "section_kiskoru": "9) Kiskorú gyermek utazik együtt",
    "kiskoru_utazik": "Az útlevélben szereplő kiskorú gyermek velem együtt utazik",

    "section_tervezett": "10) Tartózkodás tervezett időtartama és célja",
    "tartozkodas_vege": "Meddig kéri az engedélyt? (YYYY-MM-DD)",
    "tartozkodas_celja": "Tartózkodás célja",

    "section_fizetes": "11) Fizetési tranzakció",
    "tranzakcio_szam": "Elektronikus/banki befizetés tranzakciós száma. Az engedélykérelmi eljárásokban vannak fizetős eljárások, ahol előre meg kell fizetni a díjat. Ezt csak abban az esetben kell kitölteni, ha az Ön által választott eljárás díjköteles."
  }

RU = {
    **HU,
    "app_title": "📝 Заявление на вид на жительство – форма сбора данных (HU/RU)",
    "app_caption": "По введённым данным готовятся несколько документов. Просьба их сохранить и направить по электронной почте Марии Надь на эл.адрес: maria.nagy@hungaria-xxx.com.",
    "ru_latin_notice": "⚠️ Пожалуйста, заполняйте *латиницей* (A–Z, 0–9) в соответствии с документами. Текст кириллицей будет автоматически транслитерирован, кроме некоторых полей, которые будут переведены на венгерский.",
    "help_md": (
        "1) Заполните форму на венгерском или русском (желательно латиницей).\n"
        "2) Выберите шаблоны документов.\n"
        "3) Нажмите ‘Генерировать’ для скачивания DOCX."
    ),
    # ====== Hozzátartozók RU feliratai ======

    "hozz_nem": "Пол",
    "hozz_vezeteknev": "Фамилия",
    "hozz_keresztnev": "Имя",
    "hozz_rokonsag": "Степень родства",
    "hozz_szuletesi_hely": "Место рождения",
    "hozz_szuletesi_ido": "Дата рождения",
    "hozz_anyja_vezetek": "Фамилия матери",
    "hozz_anyja_kereszt": "Имя матери",
    "hozz_allamp": "Гражданство",
    "hozz_tartozkodas_e": "Проживает ли в Венгрии?",
    "hozz_okmany_szam": "Номер документа",
    
    # Поля — переводы (HU kulcsok fordítása fent átírva RU-ra)
}

# A beépített HU/RU szótárakat elérhetővé tesszük a patch-elt load_labels számára
try:
    load_labels.__dict__['_HU'] = HU
    load_labels.__dict__['_RU'] = RU
except Exception:
    pass

# =========================
# Kanonikus értékek és megjelenítés
# =========================
GENDER_CANON = ["férfi", "nő"]
FAMILY_CANON = ["nőtlen/hajadon", "házas", "elvált", "özvegy"]
EDU_CANON = ["alapfokú", "középfokú", "felsőfokú"]
YESNO_CANON = ["igen", "nem"]
PASS_TYPES = ["magánútlevél", "szolgálati", "diplomata", "egyéb"]
PASS_COUNTRY = ["Magyarország", "Ukrajna", "Oroszország", "Szerbia", "egyéb"]
SZALLAS_JOGCIM = ["tulajdonos", "bérlő", "családtag", "szívességi lakáshasználó", "egyéb"]
ATVETEL_MOD = ["postai úton", "kiállító hatóságnál"]
POSTAI_CIM_TIPUS = ["kérelmező szálláshelye", "meghatalmazott kapcsolattartási címe"]

ORSZAG_JELLEGE_12 = [
    "szokasos_allam",
    "allampolgarsag_allam",
    "egyeb_allam"
]

ORSZAG_JELLEGE_12_RU = [
    "государство обычного пребывания",
    "государство гражданства",
    "иное государство"
]

CEL_ENUM = [
    "Vendég-önfoglalkoztatás", "Vendégbefektető", "Szezonális munkavállalás",
    "Beruházás megvalósítása céljából munkavállalás", "Foglalkoztatás",
    "Vendégmunkás-tartózkodási engedély", "Magyar Kártya", "EU Kék Kártya",
    "Vállalaton belüli áthelyezés", "Kutatás/kutatói mobilitás (hosszú távú)",
    "Nemzeti Kártya", "Tanulmányok/hallgatói mobilitás",
    "Álláskeresés vagy vállalkozás indítása", "Képzés", "Gyakornok",
    "Hivatalos", "Fehér Kártya", "Kiküldetés", "Gyógykezelés",
    "Önkéntes tevékenység folytatása", "Nemzeti érdek", "Családi együttélés biztosítása"
]

CEL_ENUM_DISP_HU = [
    "Vendég-önfoglalkoztatás (9.2. sz. betétlap)",
    "Vendégbefektető (9.3. sz. betétlap)",
    "Szezonális munkavállalás (9.4. sz. betétlap)",
    "Beruházás megvalósítása céljából munkavállalás (9.5. sz. betétlap)",
    "Foglalkoztatás (9.6. sz. betétlap)",
    "Vendégmunkás-tartózkodási engedély (9.7. sz. betétlap)",
    "Magyar Kártya (9.8. sz. betétlap)",
    "EU Kék Kártya (9.9. sz. betétlap)",
    "Vállalaton belüli áthelyezés (9.10. sz. betétlap)",
    "Kutatás vagy kutatói mobilitás (hosszú távú) (9.11. sz. betétlap)",
    "Nemzeti Kártya (9.12. sz. betétlap)",
    "Tanulmányok folytatása vagy hallgatói mobilitás (9.13. sz. betétlap)",
    "Álláskeresés vagy vállalkozás indítás (9.14. sz. betétlap)",
    "Képzés (9.15. sz. betétlap)",
    "Gyakornok (9.16. sz. betétlap)",
    "Hivatalos (9.17. sz. betétlap)",
    "Fehér Kártya (9.18. sz. betétlap)",
    "Kiküldetés (9.19. sz. betétlap)",
    "Gyógykezelés (9.20. sz. betétlap)",
    "Önkéntes tevékenység folytatása (9.21. sz. betétlap)",
    "Tartózkodási engedély nemzeti érdekből (9.22. sz. betétlap)",
    "Családi együttélés biztosítása (9.23. sz. betétlap)"
]

CEL_ENUM_DISP_RU = [
    "Самозанятость (гость) (приложение 9.2.)",
    "Инвестор (гость) (приложение 9.3.)",
    "Сезонная работа (приложение 9.4.)",
    "Работа для реализации инвестпроекта (приложение 9.5.)",
    "Трудоустройство (приложение 9.6.)",
    "Разрешение для гостевых работников (приложение 9.7.)",
    "Hungarian Card (приложение 9.8.)",
    "EU Blue Card (приложение 9.9.)",
    "Внутрифирменный перевод (приложение 9.10.)",
    "Исследования или исследовательская мобильность (долгосрочная) (приложение 9.11.)",
    "National Card (приложение 9.12.)",
    "Обучение или студенческая мобильность (приложение 9.13.)",
    "Поиск работы или открытие бизнеса (приложение 9.14.)",
    "Обучение (приложение 9.15.)",
    "Стажёр (приложение 9.16.)",
    "Официальная цель (приложение 9.17.)",
    "White Card (приложение 9.18.)",
    "Командирование (приложение 9.19.)",
    "Лечение (приложение 9.20.)",
    "Волонтёрская деятельность (приложение 9.21.)",
    "В национальных интересах (приложение 9.22.)",
    "Воссоединение семьи (приложение 9.23.)"
]

CITIZENSHIP_CANON = ["magyar", "ukrán", "orosz", "szerb", "egyéb"]

# Megjelenítendő címkék RU felületen
GENDER_DISP_RU = ["мужской", "женский"]
FAMILY_DISP_RU = ["неженат/незамужем", "женат/замужем", "в разводе", "вдовец/вдова"]
EDU_DISP_RU = ["начальное", "среднее", "высшее"]
YESNO_DISP_RU = ["да", "нет"]
PASS_TYPES_RU = ["обычный", "служебный", "дипломатический", "прочее"]
PASS_COUNTRY_RU = ["Венгрия", "Украина", "Россия", "Сербия", "другая страна"]
SZALLAS_JOGCIM_RU = ["собственник", "арендатор", "член семьи", "безвозмездное пользование", "прочее"]
ATVETEL_MOD_RU = ["почтовой отправкой", "в выдавшем органе"]
POSTAI_CIM_TIPUS_RU = ["адрес проживания заявителя", "адрес доверенного лица"]
CEL_ENUM_RU = [
    "Самозанятость (гость)", "Инвестор (гость)", "Сезонная работа",
    "Работа для реализации инвестпроекта", "Трудоустройство",
    "Разрешение для гостевых работников", "Hungarian Card", "EU Blue Card",
    "Внутрифирменный перевод", "Исследования/мобильность (долгоср.)",
    "National Card", "Учёба/студ. мобильность",
    "Поиск работы/открытие бизнеса", "Обучение", "Стажёр",
    "Официальная", "White Card", "Командирование", "Лечение",
    "Волонтёрство", "В национальных интересах", "Воссоединение семьи"
]
CITIZENSHIP_DISP_RU = ["венгерское", "украинское", "русское", "сербское", "прочее"]

EGEBIZT_OPTS = [
    "foglalkoztatási jogviszony alapján",
    "rendelkezem anyagi fedezettel a költségek fedezetére",
    "rendelkezem teljes körű egészségbiztosítással",
    "egyéb"
]

EGEBIZT_OPTS_RU = [
    "на основании трудовых отношений",
    "располагаю финансовыми средствами для покрытия расходов",
    "имею полное медицинское страхование",
    "прочее"
]

def get_localized_options(lang: str):
    if lang == "ru":
        return (
            GENDER_DISP_RU, FAMILY_DISP_RU, EDU_DISP_RU, YESNO_DISP_RU,
            PASS_TYPES_RU, SZALLAS_JOGCIM_RU, ATVETEL_MOD_RU, POSTAI_CIM_TIPUS_RU, CEL_ENUM_DISP_RU
        )
    return (
        GENDER_CANON, FAMILY_CANON, EDU_CANON, YESNO_CANON,
        PASS_TYPES, SZALLAS_JOGCIM, ATVETEL_MOD, POSTAI_CIM_TIPUS, CEL_ENUM_DISP_HU
    )

def to_canonical(lang: str, field: str, value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    mapping = {}
    if field == "gender":
        mapping = {"ru": dict(zip(GENDER_DISP_RU, GENDER_CANON))}
    elif field == "family":
        mapping = {"ru": dict(zip(FAMILY_DISP_RU, FAMILY_CANON))}
    elif field == "edu":
        mapping = {"ru": {"начальное":"alapfokú","среднее":"középfokú","высшее":"felsőfokú"}}
    elif field == "yesno":
        mapping = {"ru": {"да":"igen","нет":"nem"}}
    elif field == "passtype":
        mapping = {"ru": {"обычный":"magánútlevél","служебный":"szolgálati","дипломатический":"diplomata", "прочее":"egyéb"}}
    elif field == "szallas_jogcim":
        mapping = {"ru": {"собственник":"tulajdonos","арендатор":"bérlő","член семьи":"családtag","безвозмездное пользование":"szívességi lakáshasználó","прочее":"egyéb"}}
    elif field == "atvetel_mod":
        mapping = {"ru": {"почтовой отправкой":"postai úton","в выдавшем органе":"kiállító hatóságnál"}}
    elif field == "postai_cim_tipus":
        mapping = {"ru": {"адрес проживания заявителя":"kérelmező szálláshelye","адрес доверенного лица":"meghatalmazott kapcsolattartási címe"}}
    elif field == "cel":
        mapping = {
            "ru": dict(zip(CEL_ENUM_DISP_RU, CEL_ENUM)),
            "hu": dict(zip(CEL_ENUM_DISP_HU, CEL_ENUM))
        }
  
    elif field == "egeszseg_biztositas":
        mapping = {
            "ru": {
                "на основании трудовых отношений": "foglalkoztatási jogviszony alapján",
                "располагаю финансовыми средствами для покрытия расходов": "rendelkezem anyagi fedezettel a költségek fedezetére",
                "имею полное медицинское страхование": "rendelkezem teljes körű egészségbiztosítással",
                "прочее": "egyéb"
            }
        }

    elif field == "orszag_jellege_12":
        mapping = {
            "ru": {
                "государство обычного пребывания": "szokasos_allam",
                "государство гражданства": "allampolgarsag_allam",
                "иное государство": "egyeb_allam"
            }
        }
    return mapping.get(lang, {}).get(v, v)

# =========================
# Transzliteráció (cirill → latin) + detektálás
# =========================
CYR_TO_LAT = {
    'А':'A','Б':'B','В':'V','Г':'G','Д':'D','Е':'E','Ё':'E','Ж':'Zh','З':'Z','И':'I','Й':'I','К':'K','Л':'L','М':'M',
    'Н':'N','О':'O','П':'P','Р':'R','С':'S','Т':'T','У':'U','Ф':'F','Х':'Kh','Ц':'Ts','Ч':'Ch','Ш':'Sh','Щ':'Shch',
    'Ъ':'','Ы':'Y','Ь':'','Э':'E','Ю':'Yu','Я':'Ya','Є':'Ye','Ї':'Yi','І':'I','Ґ':'G',
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'i','к':'k','л':'l','м':'m',
    'н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh','щ':'shch',
    'ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya','є':'ye','ї':'yi','і':'i','ґ':'g'
}

def contains_cyrillic(s: str) -> bool:
    return any('\u0400' <= ch <= '\u04FF' or '\u0500' <= ch <= '\u052F' for ch in (s or ""))


def transliterate_to_latin(text: str) -> str:
    if not text:
        return text
    return ''.join(CYR_TO_LAT.get(ch, ch) for ch in text)


def transliterate_record_fields(record: dict, fields: list[str]) -> tuple[dict, bool]:
    out = dict(record)
    changed = False
    for k in fields:
        v = out.get(k, "")
        if contains_cyrillic(v):
            out[k] = transliterate_to_latin(v)
            changed = True
    return out, changed

# =========================
# Validáció
# =========================
RE_PASSPORT = re.compile(r"^[A-Z0-9]{5,15}$", re.I)
RE_DATE_YMD = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def iso_date(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    dt = parse_date(s, dayfirst=True)
    return dt.date().isoformat()


    

    ## ✅ 2️⃣ TELJES, HELYES `validate_record` (EGYBEN)
    
    
    def validate_record(r: dict, L: dict, ui_lang: str):
        errors = []
    
        # Kötelező családi és utónév
        if not ((r.get("TXT_CSALADI_NEV") or "").strip() and (r.get("TXT_UTONEV") or "").strip()):
            errors.append(L.get("err_required_name"))
    
        # Útlevélszám formátum
        if r.get("NR_UTLEVEL_SZAM") and not RE_PASSPORT.match(r["NR_UTLEVEL_SZAM"]):
            base_err = L.get("err_bad_passport")
            hint = (
                "Elvárt: 5–15 karakter, A–Z és 0–9."
                if ui_lang == "hu"
                else "Ожидается 5–15 символов латиницей/цифрами."
            )
            errors.append(f"{base_err} {hint}")
    
        return errors

   


# =========================
# DOCX sablonkezelés és ZIP
# =========================

def list_docx_templates(templates_dir: Path):
    if not templates_dir.exists():
        return []
    return sorted([p for p in templates_dir.glob("*.docx") if p.is_file()])


def render_docx_from_template(template_path: Path, context: dict) -> bytes:
    if not template_path.exists():
        raise FileNotFoundError(f"Hiányzik a Word sablon: {template_path}")
    doc = DocxTemplate(str(template_path))
    doc.render(context)
    bio = io.BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio.read()


def sanitize_for_filename(text: str) -> str:
    text = (text or "").strip()
    return text.replace(" ", "_") if text else "dokumentum"


def ascii_sanitize_filename(name: str) -> str:
    name = (name or "").strip()
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    for ch in r'\/:*?"<>\n':
        name = name.replace(ch, "_")
    return (name or "dokumentum").replace(" ", "_")

# =========================
# Titkok / környezeti változók (Azure Translator — opcionális)
# =========================

def _get_secret(name: str, default: str | None = None) -> str | None:
    if name in st.secrets:
        return str(st.secrets[name])
    return os.environ.get(name, default)


def translator_translate_to_hungarian(text: str) -> str | None:
    """Azure Translator (Text Translation v3) — RU→HU fordítás.
    Endpoint (custom, regionális): {endpoint}/translator/text/v3.0/translate?api-version=3.0&to=hu
    Fejlécek: Ocp-Apim-Subscription-Key, Ocp-Apim-Subscription-Region, Content-Type: application/json
    """
    key = _get_secret("AZURE_TRANSLATOR_KEY")
    region = _get_secret("AZURE_TRANSLATOR_REGION")
    endpoint = _get_secret("AZURE_TRANSLATOR_ENDPOINT")
    if not (key and region and endpoint and text):
        return None
    url = endpoint.rstrip("/") + "/translator/text/v3.0/translate?api-version=3.0&to=hu"
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Ocp-Apim-Subscription-Region": region,
        "Content-Type": "application/json",
    }
    body = [{"Text": text}]
    try:
        r = requests.post(url, headers=headers, json=body, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data[0]["translations"][0]["text"]
    except Exception:
        return None

# =========================
# UI – Nyelvválasztó
# =========================
if "ui_lang" not in st.session_state:
    st.session_state["ui_lang"] = "hu"
ui_lang = st.session_state["ui_lang"]
L = load_labels(ui_lang)

st.title(L["app_title"]) 

st.caption(L["app_caption"])

# Oldalsáv: sablonok
st.sidebar.header(L["sidebar_hdr_templates"])
available_templates = list_docx_templates(TEMPLATES_DIR)
if not available_templates:
    st.sidebar.warning(L["err_no_templates"])
else:
    for p in available_templates:
        st.sidebar.write(f"• {p.name}")

# Nyelvválasztó
new_lang = st.selectbox(
    L["sidebar_lang"], ["hu", "ru"], index=["hu", "ru"].index(ui_lang),
    format_func=lambda x: {"hu":"Magyar", "ru":"Русский"}.get(x, x), key="ui_lang_selector"
)
if new_lang != ui_lang:
    st.session_state["ui_lang"] = new_lang
    st.rerun()

# RU UI esetén figyelmeztetés
if ui_lang == "ru":
    st.warning(L["ru_latin_notice"])

# Lokalizált opciók
GENDER_DISP, FAMILY_DISP, EDU_DISP, YESNO_DISP, PASS_DISP, JOGCIM_DISP, ATVETEL_DISP, POSTAI_DISP, CEL_DISP = get_localized_options(ui_lang)



st.subheader(L["form_header"])

# ====== HOZZÁTARTOZÓI UI BLOKK – FORM ELŐTT ======

# Session state inicializálása
if "hozz_inputs" not in st.session_state:
    st.session_state["hozz_inputs"] = 0

# Eltartott hozzátartozók száma
hozz_count = st.number_input(
    L["hozz_count"],
    min_value=0,
    max_value=8,
    step=1,
    value=0,
    key="hozz_count_selector"
)

# Magyarázó szöveg – azonnal
if hozz_count > 0:
    if ui_lang == "ru":
        st.info("Если Вы указали, что у вас есть родственники-иждивенцы, добавьте данные о них с помощью кнопки 'Добавить'. (Если речь идет о нескольких лицах, нажмите кнопку столько раз, сколько человек вы собираетесь внести в форму.) Соответствующие поля появятся в конце формы.")
    else:
        st.info("Amennyiben megadta, hogy vannak eltartott hozzátartozói, adja hozzá a rájuk vonatkozó információt a Hozzáadás gombbal. (Ha több személyről van szó, akkor annyiszor nyomja meg a gombot, ahány fő adatait ki fogja tölteni.) A kapcsolódó mezők az űrlap végén jelennek meg.")

# Hozzáadás gomb (formon kívül!)
if st.button("➕ Hozzáadás / Добавить"):
    if st.session_state["hozz_inputs"] < hozz_count:
        st.session_state["hozz_inputs"] += 1
        

with st.form("adaturlap", clear_on_submit=False):
    # 0) Elérhetőség
    st.markdown(f"**{L['section_contact']}**")
    TXT_TELEFON = st.text_input(L["phone"], key="TXT_TELEFON")
    TXT_EMAIL = st.text_input(L["email"], key="TXT_EMAIL")


    # 1) Személyes
    st.markdown(f"**{L['section_personal']}**")

    TXT_CSALADI_NEV = render_text_field("TXT_CSALADI_NEV", L["vezeteknev"], ui_lang)
    TXT_UTONEV = render_text_field("TXT_UTONEV", L["keresztnev"], ui_lang)
    TXT_SZUL_CSALADI_NEV = render_text_field("TXT_SZUL_CSALADI_NEV", L["szuletesi_csaladi"], ui_lang)
    TXT_SZUL_UTONEV = render_text_field("TXT_SZUL_UTONEV", L["szuletesi_uto"], ui_lang)
    TXT_ANYA_CSALADI_NEV = render_text_field("TXT_ANYA_CSALADI_NEV", L["anyja_csaladi"], ui_lang)
    TXT_ANYA_UTONEV = render_text_field("TXT_ANYA_UTONEV", L["anyja_uto"], ui_lang)

    # Nem (kötelező Word X mezők miatt)
    nem_disp = st.selectbox(
        L["nem"],
        options=[""] + GENDER_DISP,
        index=0
    )
    
    # Családi állapot (kötelező Word X mezők miatt)
    csaladi_allapot_disp = st.selectbox(
        L["csaladi_allapot"],
        options=[""] + FAMILY_DISP,
        index=0
    )

    # Állampolgárság – lokalizált lista
    if ui_lang == "ru":
        allamp_opts = CITIZENSHIP_DISP_RU
        egyeb_label = "Прочее гражданство"
        egyeb_value = "прочее"
    else:
        allamp_opts = CITIZENSHIP_CANON
        egyeb_label = "Egyéb állampolgárság megnevezése"
        egyeb_value = "egyéb"

    allampolgarsag_valaszto = st.selectbox(
        L["allampolgarsag"],
        allamp_opts
    )

    egyeb_allampolgarsag = ""
    if allampolgarsag_valaszto == egyeb_value:
        egyeb_allampolgarsag = st.text_input(egyeb_label)

    allampolgarsag = (
        egyeb_allampolgarsag.strip()
        if allampolgarsag_valaszto == egyeb_value
        else allampolgarsag_valaszto
    )



    nemzetiseg = st.text_input(L["nemzetiseg"]) 
    szuletesi_datum = st.text_input(L["szuletesi_datum"], placeholder="YYYY-MM-DD")
    szuletesi_hely = st.text_input(L["szuletesi_hely"]) 
    szuletesi_orszag = st.text_input(L["szuletesi_orszag"]) 
    vegzettseg_disp = st.selectbox(L["vegzettseg"], options=[""] + EDU_DISP, index=0)
    szakkepzettseg = st.text_input(L["szakkepzettseg"], placeholder="pl. villanyszerelő / бухгалтер")
    elozo_foglalkozas = st.text_input(L["elozo_foglalkozas"], placeholder="pl. hegesztő / водитель")
   
    # 2) Útlevél
    st.markdown(f"**{L['section_passport']}**")
    NR_UTLEVEL_SZAM = render_text_field(
        "NR_UTLEVEL_SZAM",
        L["utlevel_szam"],
        ui_lang
    )
    utlevel_kiadas = st.text_input(L["utlevel_kiadas"], placeholder="YYYY-MM-DD")

    # Útlevél kiállítás helye – lokalizált lista
    if ui_lang == "ru":
        pass_country_opts = PASS_COUNTRY_RU
        egyeb_kiadas_label = "Другое место выдачи"
        egyeb_kiadas_value = "другая страна"
    else:
        pass_country_opts = PASS_COUNTRY
        egyeb_kiadas_label = "Egyéb kiadási hely"
        egyeb_kiadas_value = "egyéb"

    utlevel_hely_valaszto = st.selectbox(
        L["utlevel_helye"],
        pass_country_opts
    )

    egyeb_kiadasi_hely = ""
    if utlevel_hely_valaszto == egyeb_kiadas_value:
        egyeb_kiadasi_hely = st.text_input(egyeb_kiadas_label)

    utlevel_helye = (
        egyeb_kiadasi_hely.strip()
        if utlevel_hely_valaszto == egyeb_kiadas_value
        else utlevel_hely_valaszto
    )

    
    utlevel_tipus_disp = st.selectbox(L["utlevel_tipus"], options=[""] + PASS_DISP, index=0)
    utlevel_lejarat = st.text_input(L["utlevel_lejarat"], placeholder="YYYY-MM-DD")

    # 3) Magyarországi szálláshely
    st.markdown(f"**{L['section_szallas']}**")
    
    helyrajzi_szam = st.text_input(L["helyrajzi_szam"])
    iranyitoszam = st.text_input(L["iranyitoszam"])
    telepules = st.text_input(L["telepules"])
    kozterulet_nev = st.text_input(L["kozterulet_nev"])
    kozterulet_jelleg = st.text_input(L["kozterulet_jelleg"])
    hazszam = st.text_input(L["hazszam"])
    epulet = st.text_input(L["epulet"])
    lepcsohaz = st.text_input(L["lepcsohaz"])
    emelet = st.text_input(L["emelet"])
    ajto = st.text_input(L["ajto"])
    
    # Szálláshelyen tartózkodás jogcíme
    szallas_jogcim_disp = st.selectbox(
        L["szallas_jogcim"],
        options=[""] + (SZALLAS_JOGCIM_RU if ui_lang == "ru" else SZALLAS_JOGCIM),
        index=0,
        key="szallas_jogcim_disp"
    )
    
    # Kanonikus érték (RU -> HU visszaalakítás)
    szallas_jogcim = to_canonical(ui_lang, "szallas_jogcim", szallas_jogcim_disp)
    
    # B terv: mindig látható "egyéb" mező
    szallas_egyeb = st.text_input(
        L.get("szallas_egyeb", "Egyéb válasz esetén töltse ki:"),
        key="TXT_SZALLAS_EGYEB"
    )

    
    
    # 4) Első kérelem / Hosszabbítás
    st.markdown(f"**{L['section_elso_vagy_hossz']}**")
    
    if ui_lang == "ru":
        engedely_tipus_opts = ["", "первое обращение", "продление"]
    else:
        engedely_tipus_opts = ["", "első kérelem", "hosszabbítás"]
    
    engedely_tipus_disp = st.selectbox(
        L["engedely_tipusa"],
        options=engedely_tipus_opts,
        key="engedely_tipus_disp"
    )
    
    # belső, kanonikus érték
    if ui_lang == "ru":
        if engedely_tipus_disp == "первое обращение":
            engedely_tipus = "első kérelem"
        elif engedely_tipus_disp == "продление":
            engedely_tipus = "hosszabbítás"
        else:
            engedely_tipus = ""
    else:
        engedely_tipus = engedely_tipus_disp
    
    TXT_BEUT_HELY = render_text_field(
        "TXT_BEUT_HELY",
        L["elso_beutazas_helye"],
        ui_lang
    )
    
    beutazas_datum = st.text_input(
        L["elso_beutazas_datuma"],
        placeholder="YYYY-MM-DD"
    )
    
    NR_ENGED_SZAM = st.text_input(
        L["hossz_engedely_szam"],
        key="NR_ENGED_SZAM"
    )
    
    engedely_ervenyes = st.text_input(
        L["hossz_engedely_ervenyes"],
        placeholder="YYYY-MM-DD"
    )


    # 5) Okmány átvétele
    st.markdown(f"**{L['section_atvetel']}**")
    atvetel_mod_disp = st.selectbox(L["atvetel_mod"], options=[""] + ATVETEL_DISP, index=0)
    postai_cim_tipus_disp = st.selectbox(L["postai_cim_tipus"], options=[""] + POSTAI_DISP, index=0)

    
    # 6) Teljes körű egészségbiztosítás
    st.markdown(f"**{L['section_egeszseg']}**")
    
    egeszseg_biztositas_disp = st.selectbox(
        L["egeszseg_biztositas"],
        options=[""] + (EGEBIZT_OPTS_RU if ui_lang == "ru" else EGEBIZT_OPTS),
        index=0,
        key="egeszseg_biztositas_disp"
    )
    
    # Kanonikus érték (RU -> HU visszaalakítás)
    egeszseg_biztositas = to_canonical(ui_lang, "egeszseg_biztositas", egeszseg_biztositas_disp)
    
    # „egyéb” esetén kiegészítő szövegmező
    egeszseg_egyeb = st.text_input(
        L.get("egeszseg_egyeb", "Egyéb esetén töltse ki:"),
        key="TXT_EGEBIZT_EGYEB"
    )

    # 7) Vissza-/továbbutazás
    st.markdown(f"**{L['section_visszaut']}**")

    # Vissza-/továbbutazás országa
    # Vissza-/továbbutazás országa
    TXT_VISSZA_UTAZASI_ORSZAG = render_text_field(
        "TXT_VISSZA_UTAZASI_ORSZAG",
        L["visszaut_orszag"],
        ui_lang
    )
    
    # Ez az ország:
    orszag_jellege_12_options = [
        "",
        "szokasos_allam",
        "allampolgarsag_allam",
        "egyeb_allam"
    ]
    
    def orszag_jellege_12_label(v):
        labels = {
            "": "",
            "szokasos_allam": L["orszag_jellege_12_szokasos"],
            "allampolgarsag_allam": L["orszag_jellege_12_allamp"],
            "egyeb_allam": L["orszag_jellege_12_egyeb"],
        }
        return labels.get(v, v)
    
    orszag_jellege_12 = st.selectbox(
        L["orszag_jellege_12"],
        options=orszag_jellege_12_options,
        index=0,
        format_func=orszag_jellege_12_label,
        key="orszag_jellege_12"
    )
    
    # B terv: mindig látható két statikus mező
    enged_tipus_static = st.text_input(
        L["txt_12_enged_tipus_static"],
        key="enged_tipus_static"
    )
    
    enged_szam_static = st.text_input(
        L["txt_12_enged_szam_static"],
        key="enged_szam_static"
    )
    TXT_KOZLEKEDESI_ESZKOZ = render_text_field(
        "TXT_KOZLEKEDESI_ESZKOZ", L["kozlekedesi_eszkoz"], ui_lang
    )
    
    van_utlevel_disp = st.selectbox(
        L["van_utlevel"],
        options=[""] + YESNO_DISP,
        index=0,
        key="van_utlevel_disp"
    )

    
        
    van_vizum_disp = st.selectbox(
        L["van_vizum"],
        options=[""] + YESNO_DISP,
        index=0,
        key="van_vizum_disp"
    )
    
    van_menetjegy_disp = st.selectbox(
        L["van_menetjegy"],
        options=[""] + YESNO_DISP,
        index=0,
        key="van_menetjegy_disp"
    )
    
    van_anyagi_fedezet_disp = st.selectbox(
        L["van_anyagi_fedezet"],
        options=[""] + YESNO_DISP,
        index=0,
        key="van_anyagi_fedezet_disp"
    )
    
    fedezet_osszeg = st.text_input(
        L["fedezet_osszeg"],
        placeholder="pl. 2000 EUR"
    )

    # 8) Egyéb adatok
    st.markdown(f"**{L['section_egyeb']}**")
    elozo_orszag = st.text_input(L["elozo_orszag"]) 
    elozo_telepules = st.text_input(L["elozo_telepules"]) 
    elozo_cim = st.text_input(L["elozo_cim"]) 
    mas_schengen_okmany_disp = st.selectbox(L["mas_schengen_okmany"], options=[""] + YESNO_DISP, index=0)
    mas_schengen_tipus = st.text_input(L["mas_schengen_tipus"]) 
    mas_schengen_szam = st.text_input(L["mas_schengen_szam"]) 
    mas_schengen_ervenyes = st.text_input(L["mas_schengen_ervenyes"], placeholder="YYYY-MM-DD")

    volt_elutasitas_disp = st.selectbox(L["volt_elutasitas"], options=[""] + YESNO_DISP, index=0)
    volt_buntetve_disp = st.selectbox(L["volt_buntetve"], options=[""] + YESNO_DISP, index=0)
    buntet_reszletek = st.text_area(L["buntet_reszletek"], height=80)
    volt_kiutasitas_disp = st.selectbox(L["volt_kiutasitas"], options=[""] + YESNO_DISP, index=0)
    kiutasitas_datum = st.text_input(L["kiutasitas_datum"], placeholder="YYYY-MM-DD")
    fert_beteg_disp = st.selectbox(L["fert_beteg"], options=[""] + YESNO_DISP, index=0)
    kap_ellatas_disp = st.selectbox(L["kap_ellatas"], options=[""] + YESNO_DISP, index=0)

    # 9) Kiskorú
    st.markdown(f"**{L['section_kiskoru']}**")
    kiskoru_utazik_disp = st.selectbox(L["kiskoru_utazik"], options=[""] + YESNO_DISP, index=0)

    # 10) Tervezett időtartam és cél
    st.markdown(f"**{L['section_tervezett']}**")
    tartozkodas_vege = st.text_input(L["tartozkodas_vege"], placeholder="YYYY-MM-DD")
    tartozkodas_celja_disp = st.selectbox(L["tartozkodas_celja"], options=[""] + CEL_DISP, index=0)

    # Betétlap száma a kiválasztott célhoz
    betetlap_szam = st.text_input(
        L["betetlap_szam"],
        placeholder="pl. 9.14",
        key="TXT_BETETLAP_SZAM"
    )
    
    # 11) Fizetési tranzakció
    st.markdown(f"**{L['section_fizetes']}**")
    NR_FIZETES_TRANZAKCIO = st.text_input(
        L["tranzakcio_szam"], key="NR_FIZETES_TRANZAKCIO"
    )

   
    # ====== HOZZÁTARTOZÓK – DINAMIKUS MEZŐK A FORMON BELÜL (HU/RU i18n) ======
    
    hozz = []
    
    # I18N listák
    ROKONSAG_HU = ["szülő", "gyermek", "házastárs", "testvér", "egyéb"]
    ROKONSAG_RU = ["родитель", "ребенок", "супруг(а)", "брат/сестра", "прочее"]
    
    HOZZ_NEM_HU = ["férfi", "nő", "egyéb"]
    HOZZ_NEM_RU = ["мужской", "женский", "прочее"]
    
    # Mezőfeliratok HU/RU i18n kulcsok
    label_nem          = L.get("hozz_nem", "Nem")
    label_vezetek      = L.get("hozz_vezeteknev", "Vezetéknév")
    label_kereszt      = L.get("hozz_keresztnev", "Keresztnév")
    label_rokon        = L.get("hozz_rokonsag", "Rokonsági fok")
    label_szulhely     = L.get("hozz_szuletesi_hely", "Születési hely")
    label_szulido      = L.get("hozz_szuletesi_ido", "Születési idő")
    label_anyja_vez    = L.get("hozz_anyja_vezetek", "Anyja vezetéknév")
    label_anyja_ker    = L.get("hozz_anyja_kereszt", "Anyja keresztnév")
    label_allamp       = L.get("hozz_allamp", "Állampolgárság")
    label_tartozkodas  = L.get("hozz_tartozkodas_e", "Magyarországon tartózkodik-e?")
    label_okmany       = L.get("hozz_okmany_szam", "Okmányszám")
    
    # Nyelvfüggő választékok
    nem_opts      = HOZZ_NEM_HU if ui_lang == "hu" else HOZZ_NEM_RU
    rokonsag_opts = ROKONSAG_HU if ui_lang == "hu" else ROKONSAG_RU
    igen_nem_opts = ["igen", "nem"] if ui_lang == "hu" else ["да", "нет"]
    
    # Dinamikus hozzátartozói mezők (session_state["hozz_inputs"])
    for i in range(st.session_state.get("hozz_inputs", 0)):
        st.markdown(f"### {i+1}. {L['section_hozzatartozo']}")
    
        hozz_nem = st.selectbox(
            f"{label_nem} #{i+1}",
            nem_opts,
            key=f"h_nem_{i}"
        )
    
        vezetek = st.text_input(
            f"{label_vezetek} #{i+1}",
            key=f"h_vezetek_{i}"
        )
    
        kereszt = st.text_input(
            f"{label_kereszt} #{i+1}",
            key=f"h_kereszt_{i}"
        )
    
        rokonsag = st.selectbox(
            f"{label_rokon} #{i+1}",
            rokonsag_opts,
            key=f"h_rok_{i}"
        )
    
        szul_hely = st.text_input(
            f"{label_szulhely} #{i+1}",
            key=f"h_szulhely_{i}"
        )
    
        szul_ido = st.text_input(
            f"{label_szulido} #{i+1}",
            placeholder="YYYY-MM-DD",
            key=f"h_szulido_{i}"
        )
    
        anyja_vez = st.text_input(
            f"{label_anyja_vez} #{i+1}",
            key=f"h_anyja_vez_{i}"
        )
    
        anyja_ker = st.text_input(
            f"{label_anyja_ker} #{i+1}",
            key=f"h_anyja_ker_{i}"
        )
    
        allamp = st.text_input(
            f"{label_allamp} #{i+1}",
            key=f"h_allamp_{i}"
        )
    
        tartozkodas_e = st.selectbox(
            f"{label_tartozkodas} #{i+1}",
            igen_nem_opts,
            key=f"h_tartozik_{i}"
        )
    
        okmany = st.text_input(
            f"{label_okmany} #{i+1}",
            key=f"h_okmany_{i}"
        )
    
        # A mezők összegyűjtése strukturált JSON-hoz
        hozz.append({
            "nem": hozz_nem,
            "vezeteknev": vezetek,
            "keresztnev": kereszt,
            "rokonsagi_fok": rokonsag,
            "szuletesi_hely": szul_hely,
            "szuletesi_ido": szul_ido,
            "anyja_vezetek": anyja_vez,
            "anyja_kereszt": anyja_ker,
            "allampolgarsag": allamp,
            "tartozkodik_e": to_canonical(ui_lang, "yesno", tartozkodas_e),
            "okmany_szam": okmany
        })
    
    # 12) Sablonválasztó szekció
    st.markdown(f"**{L['select_templates']}**")

    
    # Sablonválasztás
    template_labels = [p.name for p in available_templates]
    defaults = [name for name in template_labels if name in DEFAULT_TEMPLATE_NAMES]
    selected_labels = st.multiselect(
    "",
    options=template_labels,
    default=defaults
    )
   
    submitted = st.form_submit_button(L["btn_generate"])



# =========================
# Beküldés feldolgozása
# =========================


if submitted:
    errors = []
    # Eltartottak születési ideje – csak YYYY-MM-DD formátum fogadható el
    for i, h in enumerate(hozz, start=1):
        d = (h.get("szuletesi_ido") or "").strip()
        if d and not RE_DATE_YMD.match(d):
            errors.append(f"{i}. eltartott születési ideje csak YYYY-MM-DD formátumban adható meg.")
    if not available_templates:
        errors.append(L["err_no_templates"])
    if not selected_labels:
        errors.append(L["err_no_selection"])
    

    # display -> canonical
    nem = to_canonical(ui_lang, "gender", nem_disp)
    csaladi_allapot = to_canonical(ui_lang, "family", csaladi_allapot_disp)
    vegzettseg = to_canonical(ui_lang, "edu", vegzettseg_disp)
    utlevel_tipus = to_canonical(ui_lang, "passtype", utlevel_tipus_disp)
    szallas_jogcim = to_canonical(ui_lang, "szallas_jogcim", szallas_jogcim_disp)
    atvetel_mod = to_canonical(ui_lang, "atvetel_mod", atvetel_mod_disp)
    postai_cim_tipus = to_canonical(ui_lang, "postai_cim_tipus", postai_cim_tipus_disp)
    egeszseg_biztositas = to_canonical(ui_lang, "egeszseg_biztositas", egeszseg_biztositas_disp)
    van_utlevel = to_canonical(ui_lang, "yesno", van_utlevel_disp)
    van_vizum = to_canonical(ui_lang, "yesno", van_vizum_disp)
    van_menetjegy = to_canonical(ui_lang, "yesno", van_menetjegy_disp)
    van_anyagi_fedezet = to_canonical(ui_lang, "yesno", van_anyagi_fedezet_disp)
    mas_schengen_okmany = to_canonical(ui_lang, "yesno", mas_schengen_okmany_disp)
    volt_elutasitas = to_canonical(ui_lang, "yesno", volt_elutasitas_disp)
    volt_buntetve = to_canonical(ui_lang, "yesno", volt_buntetve_disp)
    volt_kiutasitas = to_canonical(ui_lang, "yesno", volt_kiutasitas_disp)
    fert_beteg = to_canonical(ui_lang, "yesno", fert_beteg_disp)
    kap_ellatas = to_canonical(ui_lang, "yesno", kap_ellatas_disp)
    kiskoru_utazik = to_canonical(ui_lang, "yesno", kiskoru_utazik_disp)
    tartozkodas_celja = to_canonical(ui_lang, "cel", tartozkodas_celja_disp)

    # ====== Hozzátartozók segédfüggvények ======
    
    def get_elt(i, key, default=""):
        try:
            return hozz[i].get(key, default)
        except IndexError:
            return ""
    
    def split_date(d):
        return (d[:4], d[5:7], d[8:10]) if d and len(d) >= 10 else ("", "", "")

            
    record = {

        # ---- Első kérelem / Hosszabbítás (Word kompatibilis) ----
        # 4) Első kérelem / Hosszabbítás – Word logika
        
        # X mezők
        "X_ENGED_ELSO": "X" if engedely_tipus == "első kérelem" else "",
        "X_ENGED_HOSSZ": "X" if engedely_tipus == "hosszabbítás" else "",
        
        # Első kérelemhez tartozó mezők – csak akkor töltjük
        "TXT_BEUT_HELY": (TXT_BEUT_HELY or "").strip() if engedely_tipus == "első kérelem" else "",
        "DT_BEUT_EV": beutazas_datum[:4] if (engedely_tipus == "első kérelem" and beutazas_datum) else "",
        "DT_BEUT_HO": beutazas_datum[5:7] if (engedely_tipus == "első kérelem" and beutazas_datum) else "",
        "DT_BEUT_NAP": beutazas_datum[8:10] if (engedely_tipus == "első kérelem" and beutazas_datum) else "",
        
        # Hosszabbításhoz tartozó mezők – csak akkor töltjük
        "NR_ENGED_SZAM": (NR_ENGED_SZAM or "").strip() if engedely_tipus == "hosszabbítás" else "",
        "DT_ENGED_ERV_EV": engedely_ervenyes[:4] if (engedely_tipus == "hosszabbítás" and engedely_ervenyes) else "",
        "DT_ENGED_ERV_HO": engedely_ervenyes[5:7] if (engedely_tipus == "hosszabbítás" and engedely_ervenyes) else "",
        "DT_ENGED_ERV_NAP": engedely_ervenyes[8:10] if (engedely_tipus == "hosszabbítás" and engedely_ervenyes) else "",
        
        # Kapcsolattartás
        "TXT_TELEFON": (TXT_TELEFON or "").strip(),
        "TXT_EMAIL": (TXT_EMAIL or "").strip(),

        # személyes adatok
        
        "TXT_CSALADI_NEV": (TXT_CSALADI_NEV or "").strip(),
        "TXT_UTONEV": (TXT_UTONEV or "").strip(),
        "TXT_SZUL_CSALADI_NEV": (TXT_SZUL_CSALADI_NEV or "").strip(),
        "TXT_SZUL_UTONEV": (TXT_SZUL_UTONEV or "").strip(),
        "TXT_ANYA_CSALADI_NEV": (TXT_ANYA_CSALADI_NEV or "").strip(),
        "TXT_ANYA_UTONEV": (TXT_ANYA_UTONEV or "").strip(),

        # --- Nem (X kerül a megfelelő négyzetbe) ---
        "X_NEM_FERFI": "X" if nem == "férfi" else "",
        "X_NEM_NO": "X" if nem == "nő" else "",

        # --- Családi állapot (X mezők) ---
        "X_ALLAPOT_NOTLEN_HAJADON": "X" if csaladi_allapot == "nőtlen/hajadon" else "",
        "X_ALLAPOT_HAZAS": "X" if csaladi_allapot == "házas" else "",
        "X_ALLAPOT_ELVALT": "X" if csaladi_allapot == "elvált" else "",
        "X_ALLAPOT_OZVEGY": "X" if csaladi_allapot == "özvegy" else "",

        # --- Iskolai végzettség (X mezők) ---
        "X_ISKOLA_ALAP": "X" if vegzettseg == "alapfokú" else "",
        "X_ISKOLA_KOZEP": "X" if vegzettseg == "középfokú" else "",
        "X_ISKOLA_FELSO": "X" if vegzettseg == "felsőfokú" else "",
                        
        "DT_SZUL_EV": szuletesi_datum[:4] if szuletesi_datum else "",
        "DT_SZUL_HO": szuletesi_datum[5:7] if szuletesi_datum else "",
        "DT_SZUL_NAP": szuletesi_datum[8:10] if szuletesi_datum else "",
        "TXT_ALLAMPOLGARSAG": (allampolgarsag or "").strip(),
        "TXT_NEMZETISEG": (nemzetiseg or "").strip(),
        "TXT_SZUL_HELY": (szuletesi_hely or "").strip(),
        "TXT_SZUL_ORSZAG": (szuletesi_orszag or "").strip(),
        "TXT_SZAKKEPZETTSEG": (szakkepzettseg or "").strip(),

        "TXT_ELOZO_FOGLALKOZAS": (elozo_foglalkozas or "").strip(),
        
        
        # útlevél
        
        # --- Útlevél adatok (Word kompatibilis) ---

        # Útlevél száma
        "NR_UTLEVEL_SZAM": (NR_UTLEVEL_SZAM or "").strip(),
        
        # Kiállítás helye
        "TXT_UTLEVEL_KIALL_HELY": (utlevel_helye or "").strip(),
        
        # Kiállítás ideje (év / hó / nap)
        "DT_UTLEVEL_KIALL_EV": utlevel_kiadas[:4] if utlevel_kiadas else "",
        "DT_UTLEVEL_KIALL_HO": utlevel_kiadas[5:7] if utlevel_kiadas else "",
        "DT_UTLEVEL_KIALL_NAP": utlevel_kiadas[8:10] if utlevel_kiadas else "",
        
        # Érvényesség vége
        "DT_UTLEVEL_ERV_EV": utlevel_lejarat[:4] if utlevel_lejarat else "",
        "DT_UTLEVEL_ERV_HO": utlevel_lejarat[5:7] if utlevel_lejarat else "",
        "DT_UTLEVEL_ERV_NAP": utlevel_lejarat[8:10] if utlevel_lejarat else "",
        
        # Útlevél típusa – X a megfelelő helyre
        "X_UTLEVEL_MAGAN": "X" if utlevel_tipus == "magánútlevél" else "",
        "X_UTLEVEL_SZOLG": "X" if utlevel_tipus == "szolgálati" else "",
        "X_UTLEVEL_DIPLO": "X" if utlevel_tipus == "diplomata" else "",
        "X_UTLEVEL_EGYEB": "X" if utlevel_tipus == "egyéb" else "",

        
        # Szálláshely – cím adatok (Word mezők)
        "TXT_HRSZ": (helyrajzi_szam or "").strip(),
        "TXT_IRSZAM": (iranyitoszam or "").strip(),
        "TXT_TELEPULES": (telepules or "").strip(),
        "TXT_KOZTERULET_NEV": (kozterulet_nev or "").strip(),
        "TXT_KOZTERULET_JELLEG": (kozterulet_jelleg or "").strip(),
        "TXT_HAZSZAM": (hazszam or "").strip(),
        "TXT_EPULET": (epulet or "").strip(),
        "TXT_LEPCSO": (lepcsohaz or "").strip(),
        "TXT_EMELET": (emelet or "").strip(),
        "TXT_AJTO": (ajto or "").strip(),


        # Szálláshelyen tartózkodás jogcíme – Word X mezők
        "X_SZALLAS_TULAJ": "X" if szallas_jogcim == "tulajdonos" else "",
        "X_SZALLAS_BERLO": "X" if szallas_jogcim == "bérlő" else "",
        "X_SZALLAS_CSALADTAG": "X" if szallas_jogcim == "családtag" else "",
        "X_SZALLAS_SZIVES": "X" if szallas_jogcim == "szívességi lakáshasználó" else "",
        "X_SZALLAS_EGYEB": "X" if szallas_jogcim == "egyéb" else "",
        
        # Egyéb jogcím szövege       
        "TXT_SZALLAS_EGYEB": (szallas_egyeb or "").strip() if szallas_jogcim == "egyéb" else "",
               
        # Okmány átvétele – Word X mezők
        "X_ATVETEL_POSTA": "X" if atvetel_mod == "postai úton" else "",
        "X_ATVETEL_SZEMELY": "X" if atvetel_mod == "kiállító hatóságnál" else "",
        
        "X_POSTA_SZALLASHELY": "X" if postai_cim_tipus == "kérelmező szálláshelye" else "",
        "X_POSTA_MEGHATALMAZOTT": "X" if postai_cim_tipus == "meghatalmazott kapcsolattartási címe" else "",
        
        
        # Egészségbiztosítás – Word X mezők
        "X_EGEBIZT_FOGL": "X" if egeszseg_biztositas == "foglalkoztatási jogviszony alapján" else "",
        "X_EGEBIZT_FEDEZET": "X" if egeszseg_biztositas == "rendelkezem anyagi fedezettel a költségek fedezetére" else "",
        "X_EGEBIZT_TELJESKORU": "X" if egeszseg_biztositas == "rendelkezem teljes körű egészségbiztosítással" else "",
        "X_EGEBIZT_EGYEB": "X" if egeszseg_biztositas == "egyéb" else "",
        
        # „Egyéb” szöveg
        "TXT_EGEBIZT_EGYEB": (egeszseg_egyeb or "").strip() if egeszseg_biztositas == "egyéb" else "",
        
        # visszautazás
        
        "TXT_VISSZA_UTAZASI_ORSZAG": (TXT_VISSZA_UTAZASI_ORSZAG or "").strip(),
        "TXT_KOZLEKEDESI_ESZKOZ": (TXT_KOZLEKEDESI_ESZKOZ or "").strip(),

        
        # Vissza-/továbbutazás – Word X mezők
        
        # Van útlevele?
        "X_UTLEVEL_IGEN": "X" if van_utlevel == "igen" else "",
        "X_UTLEVEL_NEM": "X" if van_utlevel == "nem" else "",
        
        # Van vízuma?
        "X_VIZUM_IGEN": "X" if van_vizum == "igen" else "",
        "X_VIZUM_NEM": "X" if van_vizum == "nem" else "",
        
        # Van menetjegye?
        "X_MENETJEGY_IGEN": "X" if van_menetjegy == "igen" else "",
        "X_MENETJEGY_NEM": "X" if van_menetjegy == "nem" else "",
        
        # Van anyagi fedezete?
        "X_ANYAGI_FEDEZET_IGEN": "X" if van_anyagi_fedezet == "igen" else "",
        "X_ANYAGI_FEDEZET_NEM": "X" if van_anyagi_fedezet == "nem" else "",
        "TXT_ANYAGI_FEDEZET_OSSZEG": (fedezet_osszeg or "").strip(),
        
        # hozzátartozók
        "hozzatartozok_json": json.dumps(hozz, ensure_ascii=False),

           
        
        # egyéb adatok
        # Előző tartózkodás (Word szövegmezők)
        "TXT_ELOZO_TART_ORSZAG": (elozo_orszag or "").strip(),
        "TXT_ELOZO_TART_TELEPULES": (elozo_telepules or "").strip(),
        "TXT_ELOZO_TART_KOZTERULET": (elozo_cim or "").strip(),
        # Más schengeni okmány – Word X mezők
        "X_SCHENGEN_OKMANY_IGEN": "X" if mas_schengen_okmany == "igen" else "",
        "X_SCHENGEN_OKMANY_NEM": "X" if mas_schengen_okmany == "nem" else "",
        
        # Más schengeni okmány érvényesség dátuma (Word év / hó / nap)
        "DT_SCHENGEN_ERV_EV": mas_schengen_ervenyes[:4] if (mas_schengen_okmany == "igen" and mas_schengen_ervenyes) else "",
        "DT_SCHENGEN_ERV_HO": mas_schengen_ervenyes[5:7] if (mas_schengen_okmany == "igen" and mas_schengen_ervenyes) else "",
        "DT_SCHENGEN_ERV_NAP": mas_schengen_ervenyes[8:10] if (mas_schengen_okmany == "igen" and mas_schengen_ervenyes) else "",
        "TXT_SCHENGEN_ENGED_TIPUS": (mas_schengen_tipus or "").strip() if mas_schengen_okmany == "igen" else "",
        "NR_SCHENGEN_ENGED_SZAM": (mas_schengen_szam or "").strip() if mas_schengen_okmany == "igen" else "",
        
        # Elutasítás
        "X_ELUTASITOTT_IGEN": "X" if volt_elutasitas == "igen" else "",
        "X_ELUTASITOTT_NEM": "X" if volt_elutasitas == "nem" else "",
        
        # Büntetettség
        "X_BUNTETT_IGEN": "X" if volt_buntetve == "igen" else "",
        "X_BUNTETT_NEM": "X" if volt_buntetve == "nem" else "",
        
        # Kiutasítás
        "X_KIUTASITOTT_IGEN": "X" if volt_kiutasitas == "igen" else "",
        "X_KIUTASITOTT_NEM": "X" if volt_kiutasitas == "nem" else "",
        
        # Kiutasítás dátuma (Word év / hó / nap)
        "DT_KIUTASIT_EV": kiutasitas_datum[:4] if (volt_kiutasitas == "igen" and kiutasitas_datum) else "",
        "DT_KIUTASIT_HO": kiutasitas_datum[5:7] if (volt_kiutasitas == "igen" and kiutasitas_datum) else "",
        "DT_KIUTASIT_NAP": kiutasitas_datum[8:10] if (volt_kiutasitas == "igen" and kiutasitas_datum) else "",
        
        "TXT_BUNTETT_RESZLETEK": (buntet_reszletek or "").strip() if volt_buntetve == "igen" else "",
    
        # Fertőző betegségek és ellátás
        "X_FERT_BETEGSEG_IGEN": "X" if fert_beteg == "igen" else "",
        "X_FERT_BETEGSEG_NEM": "X" if fert_beteg == "nem" else "",
        
        "X_EU_ELLATAS_IGEN": "X" if kap_ellatas == "igen" else "",
        "X_EU_ELLATAS_NEM": "X" if kap_ellatas == "nem" else "",
        
       
        # Kiskorú gyermek együtt utazik – Word X mezők
        "X_GYERMEK_UTAZIK_IGEN": "X" if kiskoru_utazik == "igen" else "",
        "X_GYERMEK_UTAZIK_NEM": "X" if kiskoru_utazik == "nem" else "",
        
        # cél
        # Tartózkodás vége – Word dátummezők
        "DT_TARTOZKODAS_EV": tartozkodas_vege[:4] if tartozkodas_vege else "",
        "DT_TARTOZKODAS_HO": tartozkodas_vege[5:7] if tartozkodas_vege else "",
        "DT_TARTOZKODAS_NAP": tartozkodas_vege[8:10] if tartozkodas_vege else "",
        
        # Tartózkodás célja – Word X mezők
        "X_CEL_VENDEG_ONFOGL": "X" if tartozkodas_celja == "Vendég-önfoglalkoztatás" else "",
        "X_CEL_VENDEG_BEF": "X" if tartozkodas_celja == "Vendégbefektető" else "",
        "X_CEL_SZEZON": "X" if tartozkodas_celja == "Szezonális munkavállalás" else "",
        "X_CEL_BERUHAZAS": "X" if tartozkodas_celja == "Beruházás megvalósítása céljából munkavállalás" else "",
        "X_CEL_FOGLALKOZTATAS": "X" if tartozkodas_celja == "Foglalkoztatás" else "",
        "X_CEL_VENDEGMUNKAS": "X" if tartozkodas_celja == "Vendégmunkás-tartózkodási engedély" else "",
        "X_CEL_MAGYAR_KARTYA": "X" if tartozkodas_celja == "Magyar Kártya" else "",
        "X_CEL_EU_KEK_KARTYA": "X" if tartozkodas_celja == "EU Kék Kártya" else "",
        "X_CEL_VALLALATON_BELULI": "X" if tartozkodas_celja == "Vállalaton belüli áthelyezés" else "",
        "X_CEL_KUTATAS": "X" if tartozkodas_celja == "Kutatás/kutatói mobilitás (hosszú távú)" else "",
        "X_CEL_NEMZETI_KARTYA": "X" if tartozkodas_celja == "Nemzeti Kártya" else "",
        "X_CEL_TANULMANY": "X" if tartozkodas_celja == "Tanulmányok/hallgatói mobilitás" else "",
        "X_CEL_ALLASKERES": "X" if tartozkodas_celja == "Álláskeresés vagy vállalkozás indítása" else "",
        "X_CEL_KEPZES": "X" if tartozkodas_celja == "Képzés" else "",
        "X_CEL_GYAKORNOK": "X" if tartozkodas_celja == "Gyakornok" else "",
        "X_CEL_HIVATALOS": "X" if tartozkodas_celja == "Hivatalos" else "",
        "X_CEL_FEHER_KARTYA": "X" if tartozkodas_celja == "Fehér Kártya" else "",
        "X_CEL_KIKULDETES": "X" if tartozkodas_celja == "Kiküldetés" else "",
        "X_CEL_GYOGYKEZELES": "X" if tartozkodas_celja == "Gyógykezelés" else "",
        "X_CEL_ONKENTES": "X" if tartozkodas_celja == "Önkéntes tevékenység folytatása" else "",
        "X_CEL_NEMZETI_ERDEK": "X" if tartozkodas_celja == "Nemzeti érdek" else "",
        "X_CEL_CSALADI": "X" if tartozkodas_celja == "Családi együttélés biztosítása" else "",

        "TXT_BETETLAP_SZAM": (betetlap_szam or "").strip(),

        
        # 12. pont – ország jellege / X logika
        "X_12_SZOKASOS_ALLAM": "X" if orszag_jellege_12 == "szokasos_allam" else "",
        "X_12_ALLAMPOLGARSAG_ALLAM": "X" if orszag_jellege_12 == "allampolgarsag_allam" else "",
        "X_12_EGYEB_ALLAM": "X" if orszag_jellege_12 == "egyeb_allam" else "",
        
        # 1. eset – csak ha szokásos tartózkodási hely szerinti állam
        "TXT_12_ENGED_TIPUS_1": (enged_tipus_static or "").strip() if orszag_jellege_12 == "szokasos_allam" else "",
        "TXT_12_ENGED_SZAM_1": (enged_szam_static or "").strip() if orszag_jellege_12 == "szokasos_allam" else "",
        
        # 3. eset – csak ha egyéb állam
        "TXT_12_ENGED_TIPUS_2": (enged_tipus_static or "").strip() if orszag_jellege_12 == "egyeb_allam" else "",
        "TXT_12_ENGED_SZAM_2": (enged_szam_static or "").strip() if orszag_jellege_12 == "egyeb_allam" else "",


        
        # fizetés
        "NR_FIZETES_TRANZAKCIO": (NR_FIZETES_TRANZAKCIO or "").strip(),
        
        # összetett név (a fájlnevekhez)
        "teljes_nev": f"{(TXT_CSALADI_NEV or '').strip()} {(TXT_UTONEV or '').strip()}".strip(),
    }

        
    # ====== ELTARTOTTAK (ELT1–ELT4) – VÉGLEGES, BIZTONSÁGOS BLOKK ======
    for idx in range(4):
        p = idx + 1
    
        # 👉 HA NINCS eltartott ezen az indexen, NEM írunk SEMMIT
        if not get_elt(idx, "vezeteknev"):
            continue
    
        # --- Szöveges mezők: fordítás cirill esetén + fallback translit ---
        record.update({
            f"TXT_ELT{p}_VEZETEKNEV":
                translit(get_elt(idx, "vezeteknev")),
    
            f"TXT_ELT{p}_KERESZTNEV":
                translit(get_elt(idx, "keresztnev")),
    
            f"TXT_ELT{p}_ROKONSAG":
                translate_or_translit(get_elt(idx, "rokonsagi_fok")),
    
            f"TXT_ELT{p}_SZUL_HELY":
                translate_or_translit(get_elt(idx, "szuletesi_hely")),
    
            f"TXT_ELT{p}_ALLAMPOLGARSAG":
                translate_or_translit(get_elt(idx, "allampolgarsag")),
    
            f"NR_ELT{p}_TARTOZK_OKMANY":
                translit(get_elt(idx, "okmany_szam")),
            
            f"X_ELT{p}_NEM_TARTOZK_MO":
                "X" if get_elt(idx, "tartozkodik_e") == "nem" else "",
        })
    
        # --- Jogcím X-elés ---
        jogcim = (get_elt(idx, "tartozkodas_jogcim") or "").strip().lower()
    
        record.update({
            f"X_ELT{p}_JOGCIM_VIZUM":
                "X" if jogcim in ["vízum", "vizum", "visa"] else "",
    
            f"X_ELT{p}_JOGCIM_TART":
                "X" if jogcim in ["tartózkodási engedély", "tartozkodasi engedely"] else "",
    
            f"X_ELT{p}_JOGCIM_EGYEB":
                "X" if jogcim in ["egyéb", "egyeb"] else "",
    
            f"TXT_ELT{p}_JOGCIM_EGYEB":
                translit(get_elt(idx, "tartozkodas_jogcim_egyeb")),
        })

        # --- ELT születési dátum (ugyanazzal a split_date-tel, mint máshol) ---
        szul_datum = get_elt(idx, "szuletesi_ido")
        ev, ho, nap = split_date(szul_datum)
        
        record.update({
            f"DT_ELT{p}_SZUL_EV": ev,
            f"DT_ELT{p}_SZUL_HO": ho,
            f"DT_ELT{p}_SZUL_NAP": nap,
        })
    
    # CIRILL SZÖVEG FORDÍTÁSA + TRANSLIT MINDIG (UI nyelvétől függetlenül)
    
    if True:
    
        # a) Foglalkozás
        job_val = record.get("TXT_ELOZO_FOGLALKOZAS", "")
        if contains_cyrillic(job_val):
            hu_job = translator_translate_to_hungarian(job_val)
            record["TXT_ELOZO_FOGLALKOZAS"] = hu_job or transliterate_to_latin(job_val)
                   
        # b) Szakképzettség
        skill_val = record.get("TXT_SZAKKEPZETTSEG", "")
        if contains_cyrillic(skill_val):
            hu_skill = translator_translate_to_hungarian(skill_val)
            record["TXT_SZAKKEPZETTSEG"] = hu_skill or transliterate_to_latin(skill_val)
          # c) Születési hely
        birth_place = record.get("TXT_SZUL_HELY", "")
        if contains_cyrillic(birth_place):
            hu_birth_place = translator_translate_to_hungarian(birth_place)
            record["TXT_SZUL_HELY"] = hu_birth_place or transliterate_to_latin(birth_place)
    
        # d) Születési ország
        birth_country = record.get("TXT_SZUL_ORSZAG", "")
        if contains_cyrillic(birth_country):
            hu_birth_country = translator_translate_to_hungarian(birth_country)
            record["TXT_SZUL_ORSZAG"] = hu_birth_country or transliterate_to_latin(birth_country)
    
        # e) Nemzetiség
        nationality = record.get("TXT_NEMZETISEG", "")
        if contains_cyrillic(nationality):
            hu_nationality = translator_translate_to_hungarian(nationality)
            record["TXT_NEMZETISEG"] = hu_nationality or transliterate_to_latin(nationality)

        # f) Egyéb állampolgárság translit/fordítás
        allampolgarsag = record.get("TXT_ALLAMPOLGARSAG", "")
        if contains_cyrillic(allampolgarsag):
            hu_ap = translator_translate_to_hungarian(allampolgarsag)
            record["TXT_ALLAMPOLGARSAG"] = hu_ap or transliterate_to_latin(allampolgarsag)

        # g) Útlevél kiadási helye, ha Egyéb
        utlevel_helye = record.get("TXT_UTLEVEL_KIALL_HELY", "")   
        if contains_cyrillic(utlevel_helye):
            hu_place = translator_translate_to_hungarian(utlevel_helye)
            record["TXT_UTLEVEL_KIALL_HELY"] = hu_place or transliterate_to_latin(utlevel_helye)

        # h) Más shengeni okmány - Engedély típusa
        mas_schengen_tipus = record.get("TXT_SCHENGEN_ENGED_TIPUS", "")   
        if contains_cyrillic(mas_schengen_tipus):
            hu_mas_schengen_tipus = translator_translate_to_hungarian(mas_schengen_tipus)
            record["TXT_SCHENGEN_ENGED_TIPUS"] = hu_mas_schengen_tipus or transliterate_to_latin(mas_schengen_tipus)       
         
        # i) Teljes körű egészségbiztosítás Egyéb megjegyzés
        egeszseg_egyeb = record.get("TXT_EGEBIZT_EGYEB", "")
        if contains_cyrillic(egeszseg_egyeb):
            hu_egeszs = translator_translate_to_hungarian(egeszseg_egyeb)
            record["TXT_EGEBIZT_EGYEB"] = hu_egeszs or transliterate_to_latin(egeszseg_egyeb)
        
        # j) Visszautazás országa és közlekedési eszköz
        visszaut_orszag = record.get("TXT_VISSZA_UTAZASI_ORSZAG", "")
        if contains_cyrillic(visszaut_orszag):
            hu_visszaut_orszag = translator_translate_to_hungarian(visszaut_orszag)
            record["TXT_VISSZA_UTAZASI_ORSZAG"] = hu_visszaut_orszag or transliterate_to_latin(visszaut_orszag)

        kozlekedesi_eszkoz = record.get("TXT_KOZLEKEDESI_ESZKOZ", "")
        if contains_cyrillic(kozlekedesi_eszkoz):
            hu_kozlekedesi_eszkoz = translator_translate_to_hungarian(kozlekedesi_eszkoz)
            record["TXT_KOZLEKEDESI_ESZKOZ"] = hu_kozlekedesi_eszkoz or transliterate_to_latin(kozlekedesi_eszkoz)
            
      
        # k) Mo-ra érkezés előtti ország
        elozo_orszag = record.get("TXT_ELOZO_TART_ORSZAG", "")
        if contains_cyrillic(elozo_orszag):
            hu_elozo_orszag = translator_translate_to_hungarian(elozo_orszag)
            record["TXT_ELOZO_TART_ORSZAG"] = hu_elozo_orszag or transliterate_to_latin(elozo_orszag)

        
        # l) Bűncselekmény részletei
        buntet_reszletek = record.get("TXT_BUNTETT_RESZLETEK", "")
        if contains_cyrillic(buntet_reszletek):
            hu_buntet_reszletek = translator_translate_to_hungarian(buntet_reszletek)
            record["TXT_BUNTETT_RESZLETEK"] = hu_buntet_reszletek or transliterate_to_latin(buntet_reszletek)

        # m) Anyagi fedezet összege
        fedezet_osszeg = record.get("TXT_ANYAGI_FEDEZET_OSSZEG", "")
        if contains_cyrillic(fedezet_osszeg):
            hu_fedezet_osszeg = translator_translate_to_hungarian(fedezet_osszeg)
            record["TXT_ANYAGI_FEDEZET_OSSZEG"] = hu_fedezet_osszeg or transliterate_to_latin(fedezet_osszeg)


        # n) Mo-i szálláshely település 
        telepules = record.get("TXT_TELEPULES", "")
        if contains_cyrillic(telepules):
            hu_telepules = translator_translate_to_hungarian(telepules)
            record["TXT_TELEPULES"] = hu_telepules or transliterate_to_latin(telepules)

         # o) Első beutazás helye 
        elso_beutazas_helye = record.get("TXT_BEUT_HELY", "")
        if contains_cyrillic(elso_beutazas_helye):
            hu_elso_beutazas_helye = translator_translate_to_hungarian(elso_beutazas_helye)
            record["TXT_BEUT_HELY"] = hu_elso_beutazas_helye or transliterate_to_latin(elso_beutazas_helye)

        # p) Szálláshely jogcíme - egyéb megnevezés
        szallas_egyeb_val = record.get("TXT_SZALLAS_EGYEB", "")
        if contains_cyrillic(szallas_egyeb_val):
            hu_szallas_egyeb = translator_translate_to_hungarian(szallas_egyeb_val)
            record["TXT_SZALLAS_EGYEB"] = hu_szallas_egyeb or transliterate_to_latin(szallas_egyeb_val)

        # q) Egészségbiztosítás - egyéb megjegyzés
        egeszseg_egyeb_val = record.get("TXT_EGEBIZT_EGYEB", "")
        if contains_cyrillic(egeszseg_egyeb_val):
            hu_egeszseg_egyeb = translator_translate_to_hungarian(egeszseg_egyeb_val)
            record["TXT_EGEBIZT_EGYEB"] = hu_egeszseg_egyeb or transliterate_to_latin(egeszseg_egyeb_val)

                
        # r) 12. pont – statikus engedély típus mező
        enged_tipus_static_val = enged_tipus_static or ""
        if contains_cyrillic(enged_tipus_static_val):
            hu_enged_tipus_static = translator_translate_to_hungarian(enged_tipus_static_val)
            enged_tipus_static = hu_enged_tipus_static or transliterate_to_latin(enged_tipus_static_val)

                    
        # s) Minden egyéb mező transliterációja
        to_trans = [
            "TXT_CSALADI_NEV",
            "TXT_UTONEV",
            "TXT_SZUL_CSALADI_NEV",
            "TXT_SZUL_UTONEV",
            "TXT_ANYA_CSALADI_NEV",
            "TXT_ANYA_UTONEV",
            "TXT_SZUL_HELY",            
            "TXT_KOZTERULET_NEV",
            "TXT_KOZTERULET_JELLEG",
            "TXT_SZALLAS_EGYEB",
            "TXT_ELOZO_TART_TELEPULES",
            "TXT_ELOZO_TART_KOZTERULET",
            "TXT_ELOZO_TART_KOZTER_JELLEG",
            "NR_FIZETES_TRANZAKCIO",
            
        ]
        
        record, _ = transliterate_record_fields(record, to_trans)
        # hozzátartozók listájában is translit
        if record.get("hozzatartozok_json"):
            try:
                lst = json.loads(record["hozzatartozok_json"]) or []
                for x in lst:
                    for k in list(x.keys()):
                        if contains_cyrillic(x.get(k, "")):
                            x[k] = transliterate_to_latin(x.get(k, ""))
                record["hozzatartozok_json"] = json.dumps(lst, ensure_ascii=False)
            except Exception:
                pass

    # Validáció előtt
    if not isinstance(errors, list):
        errors = []
        
    # Validáció + dátumnormalizálás
    #try:
    #    val_errors = validate_record(record, L, ui_lang)
    #    if isinstance(val_errors, list) and val_errors:
    #        errors.extend(val_errors)
    #except Exception as e:
        # 🔒 Soha ne álljon le az app validáció miatt
        #st.warning(f"⚠️ Validációs hiba történt, kihagyva: {e}")


    if errors:
        st.error(L["err_fix"] + "\n- " + "\n- ".join(errors))
    else:
        try:
            # Új rekord létrehozása
            saved = create_record(record)
            upsert_msg = L["succ_new"].format(id=saved.get("id"), nev=record.get("teljes_nev"))

            # Dokumentumok generálása
            generated_docs = []
            who = sanitize_for_filename(record.get("teljes_nev", "dokumentum"))
            when = datetime.now().strftime("%Y%m%d_%H%M")
            for label in selected_labels:
                tpath = next((p for p in available_templates if p.name == label), None)
                if not tpath:
                    st.error(f"A kiválasztott sablon nem található: {label}")
                    continue
                doc_bytes = render_docx_from_template(tpath, record)
                out_name = f"{tpath.stem}_{who}_{when}.docx"
                generated_docs.append((out_name, doc_bytes))

            if not generated_docs:
                st.error("Nem sikerült dokumentumot generálni.")
            else:
                st.success(L["succ_upsert"].format(msg=upsert_msg, n=len(generated_docs)))
                for fname, data in generated_docs:
                    st.download_button(
                        label=L["btn_download_doc"].format(fname=fname),
                        data=data,
                        file_name=fname,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"dl_{fname}"
                    )
                # ZIP
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for fname, data in generated_docs:
                        inner_name = ascii_sanitize_filename(Path(fname).name)
                        zf.writestr(inner_name, data)
                zip_bytes = zip_buffer.getvalue()
                zip_name = ascii_sanitize_filename(f"osszes_dokumentum_{who}_{when}.zip")
                st.download_button(
                    label=L["btn_download_zip"], data=zip_bytes, file_name=zip_name, mime="application/zip", key="dl_zip_all"
                )
        except Exception as e:
            st.error(f"Váratlan hiba történt: {e}")

# =========================
# Helyőrzők listája (a sablonokhoz) – megjelenítjük is
# =========================
PLACEHOLDERS = [

    # Kapcsolattartás
    "TXT_TELEFON",
    "TXT_EMAIL",

    # Személyes adatok
    "TXT_CSALADI_NEV",
    "TXT_UTONEV",
    "TXT_SZUL_CSALADI_NEV",
    "TXT_SZUL_UTONEV",
    "TXT_ANYA_CSALADI_NEV",
    "TXT_ANYA_UTONEV",
    "DT_SZUL_EV",
    "DT_SZUL_HO",
    "DT_SZUL_NAP",
    "TXT_SZUL_HELY",
    "TXT_SZUL_ORSZAG",
    "TXT_ALLAMPOLGARSAG",
    "TXT_NEMZETISEG",
    "TXT_SZAKKEPZETTSEG",
    "TXT_ELOZO_FOGLALKOZAS",

    # Nem – X mezők
    "X_NEM_FERFI",
    "X_NEM_NO",

    # Családi állapot – X mezők
    "X_ALLAPOT_NOTLEN_HAJADON",
    "X_ALLAPOT_HAZAS",
    "X_ALLAPOT_ELVALT",
    "X_ALLAPOT_OZVEGY",

    # Útlevél
    "NR_UTLEVEL_SZAM",
    "TXT_UTLEVEL_KIALL_HELY",
    "DT_UTLEVEL_KIALL_EV",
    "DT_UTLEVEL_KIALL_HO",
    "DT_UTLEVEL_KIALL_NAP",
    "DT_UTLEVEL_ERV_EV",
    "DT_UTLEVEL_ERV_HO",
    "DT_UTLEVEL_ERV_NAP",

    # Szálláshely
    "TXT_HRSZ",
    "TXT_IRSZAM",
    "TXT_TELEPULES",
    "TXT_KOZTERULET_NEV",
    "TXT_KOZTERULET_JELLEG",
    "TXT_HAZSZAM",
    "TXT_EPULET",
    "TXT_LEPCSO",
    "TXT_EMELET",
    "TXT_AJTO",

    # Tartózkodás vége
    "DT_TARTOZKODAS_EV",
    "DT_TARTOZKODAS_HO",
    "DT_TARTOZKODAS_NAP",

    # Fizetés
    "NR_FIZETES_TRANZAKCIO",

    # Technikai
    "teljes_nev",
    "hozzatartozok_json",
]

with st.expander("📌 Helyőrzők (templates) – kattintson a listához", expanded=False):
    st.code("\n".join(PLACEHOLDERS), language="text")

# =====================================================================
# KANONIKUS WORD / JSON MEZŐLISTA (TELJES – „236-os lista”)
# Forrás: OIF Tartózkodási engedély sablon
#
# FELHASZNÁLÁS:
# - Word sablon {{MEZŐ}} ellenőrzés
# - Streamlit key-ek validálása
# - docxtpl context ellenőrzés
# =====================================================================

# WORD_CANONICAL_FIELDS ideiglenesen kiszervezve / kikommentezve
