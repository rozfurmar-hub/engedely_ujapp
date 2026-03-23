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


# ---- Adatkezelő modul (meglévő környezetből) ----
from datakezelo import BASE_DIR, create_record, list_records, update_record

# ---- Oldal beállítás ----
st.set_page_config(page_title="Tartózkodási engedély – adatbekérő", page_icon="📝", layout="centered")

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
    "select_templates": "Válasszon sablon(oka)t",
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

    "section_elso_vagy_hossz": "Első kérelem / Hosszabbítás",
    "elso_beutazas_helye": "Első kérelemnél: beutazás helye",
    "elso_beutazas_datuma": "Első kérelemnél: beutazás ideje (YYYY-MM-DD)",
    "hossz_engedely_szam": "Hosszabbításnál: engedély száma",
    "hossz_engedely_ervenyes": "Hosszabbításnál: engedély érvényessége (YYYY-MM-DD)",

    "section_atvetel": "Okmány átvétele",
    "atvetel_mod": "Átvétel módja",
    "postai_cim_tipus": "Postai kézbesítés címe",

    "section_egeszseg": "4) Teljes körű egészségbiztosítás",
    "egeszseg_biztositas": "Rendelkezik teljes körű egészségbiztosítással?",
    "egeszseg_egyeb": "Egyéb (biztosítás típusa, megjegyzés)",

    "section_visszaut": "5) Vissza-/továbbutazás feltételei",
    "visszaut_orszag": "Vissza-/továbbutazás országa",
    "kozlekedesi_eszkoz": "Közlekedési eszköz",
    "van_utlevel": "Rendelkezik útlevéllel?",
    "van_vizum": "Rendelkezik vízummal?",
    "van_menetjegy": "Rendelkezik menetjeggyel?",
    "van_anyagi_fedezet": "Rendelkezik anyagi fedezettel?",
    "fedezet_osszeg": "Anyagi fedezet összege",

    "section_hozzatartozo": "Eltartott házastárs/gyermek/szülő (max. 8 fő)",
    "hozz_count": "Eltartott hozzátartozók száma",

    "section_egyeb": "7) Egyéb adatok",
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

    "section_kiskoru": "8) Kiskorú gyermek utazik együtt",
    "kiskoru_utazik": "Az útlevélben szereplő kiskorú gyermek velem együtt utazik",

    "section_tervezett": "9) Tartózkodás tervezett időtartama és célja",
    "tartozkodas_vege": "Meddig kéri az engedélyt? (YYYY-MM-DD)",
    "tartozkodas_celja": "Tartózkodás célja",

    "section_fizetes": "Fizetési tranzakció",
    "tranzakcio_szam": "Elektronikus/banki befizetés tranzakciós száma",
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
CITIZENSHIP_CANON = ["magyar", "ukrán", "orosz", "szerb", "egyéb"]

# Megjelenítendő címkék RU felületen
GENDER_DISP_RU = ["мужской", "женский"]
FAMILY_DISP_RU = ["неженат/незамужем", "женат/замужем", "в разводе", "вдовец/вдова"]
EDU_DISP_RU = ["начальное", "среднее", "высшее"]
YESNO_DISP_RU = ["да", "нет"]
PASS_TYPES_RU = ["обычный", "служебный", "дипломатический", "другое"]
PASS_COUNTRY_RU = ["Венгрия", "Украина", "Россия", "Сербия", "другая страна"]
SZALLAS_JOGCIM_RU = ["собственник", "арендатор", "член семьи", "безвозмездное пользование", "другое"]
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
CITIZENSHIP_DISP_RU = ["венгерское", "украинское", "русское", "сербское", "другое"]

def get_localized_options(lang: str):
    if lang == "ru":
        return (
            GENDER_DISP_RU, FAMILY_DISP_RU, EDU_DISP_RU, YESNO_DISP_RU,
            PASS_TYPES_RU, SZALLAS_JOGCIM_RU, ATVETEL_MOD_RU, POSTAI_CIM_TIPUS_RU, CEL_ENUM_RU
        )
    return (GENDER_CANON, FAMILY_CANON, EDU_CANON, YESNO_CANON,
            PASS_TYPES, SZALLAS_JOGCIM, ATVETEL_MOD, POSTAI_CIM_TIPUS, CEL_ENUM)


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
        mapping = {"ru": {"обычный":"magánútlevél","служебный":"szolgálati","дипломатический":"diplomata","другое":"egyéb"}}
    elif field == "szallas_jogcim":
        mapping = {"ru": {"собственник":"tulajdonos","арендатор":"bérlő","член семьи":"családtag","безвозмездное пользование":"szívességi lakáshasználó","другое":"egyéb"}}
    elif field == "atvetel_mod":
        mapping = {"ru": {"почтовой отправкой":"postai úton","в выдавшем органе":"kiállító hatóságnál"}}
    elif field == "postai_cim_tipus":
        mapping = {"ru": {"адрес проживания заявителя":"kérelmező szálláshelye","адрес доверенного лица":"meghatalmazott kapcsolattartási címe"}}
    elif field == "cel":
        mapping = {"ru": dict(zip(CEL_ENUM_RU, CEL_ENUM))}
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


def iso_date(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    dt = parse_date(s, dayfirst=True)
    return dt.date().isoformat()


def validate_record(r: dict, L: dict, ui_lang: str) -> list[str]:
    errors = []
    if not ((r.get("vezeteknev") or "").strip() and (r.get("keresztnev") or "").strip()):
        errors.append(L.get("err_required_name"))
    if r.get("utlevel_szam") and not RE_PASSPORT.match(r["utlevel_szam"]):
        base_err = L.get("err_bad_passport")
        hint = "Elvárt: 5–15 karakter, A–Z és 0–9." if ui_lang == "hu" else "Ожидается 5–15 символов латиницей/цифрами."
        errors.append(f"{base_err} {hint}")
    # dátumok normalizálása és jövőbeni követelmények
    for key in [
        "szuletesi_datum", "utlevel_kiadas", "utlevel_lejarat", "elso_beutazas_datuma",
        "hossz_engedely_ervenyes", "mas_schengen_ervenyes", "kiutasitas_datum", "tartozkodas_vege"
    ]:
        if r.get(key):
            try:
                r[key] = iso_date(r[key])
            except Exception:
                errors.append(L.get("err_invalid_date").format(field=key))
    today = date.today().isoformat()
    for key in ["utlevel_lejarat", "tartozkodas_vege"]:
        if r.get(key) and r[key] <= today:
            errors.append(L.get("err_past_date").format(field=key))
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

floating_chat()

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
    phone = st.text_input(L["phone"], placeholder="+36…")
    email = st.text_input(L["email"], placeholder="nev@example.com")

    # 1) Személyes
    st.markdown(f"**{L['section_personal']}**")
    vezeteknev = st.text_input(L["vezeteknev"])  # családi
    show_field_help("vezeteknev", ui_lang)
    keresztnev = st.text_input(L["keresztnev"])  # utónév
    show_field_help("keresztnev", ui_lang)
    szuletesi_csaladi = st.text_input(L["szuletesi_csaladi"])
    show_field_help("szuletesi_csaladi", ui_lang)
    szuletesi_uto = st.text_input(L["szuletesi_uto"]) 
    show_field_help("szuletesi_uto", ui_lang)
    anyja_csaladi = st.text_input(L["anyja_csaladi"])
    show_field_help("anyja_csaladi", ui_lang)
    anyja_uto = st.text_input(L["anyja_uto"]) 
    show_field_help("anyja_uto", ui_lang)
    nem_disp = st.selectbox(L["nem"], options=[""] + GENDER_DISP, index=0)
    csaladi_allapot_disp = st.selectbox(L["csaladi_allapot"], options=[""] + FAMILY_DISP, index=0)
    
    # Állampolgárság – lokalizált lista
    if ui_lang == "ru":
        allamp_opts = CITIZENSHIP_DISP_RU
        egyeb_label = "Другое гражданство"
        egyeb_value = "другое"
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
    show_field_help("elozo_foglalkozas", ui_lang)

    # 2) Útlevél
    st.markdown(f"**{L['section_passport']}**")
    utlevel_szam = st.text_input(L["utlevel_szam"], placeholder="AB1234567")
    show_field_help("elozo_foglalkozas", ui_lang)
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

    # 3) Szálláshely
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
    szallas_jogcim_disp = st.selectbox(L["szallas_jogcim"], options=[""] + JOGCIM_DISP, index=0)

    # Első/hosszabbítás
    st.markdown(f"**{L['section_elso_vagy_hossz']}**")
    elso_beutazas_helye = st.text_input(L["elso_beutazas_helye"]) 
    elso_beutazas_datuma = st.text_input(L["elso_beutazas_datuma"], placeholder="YYYY-MM-DD")
    hossz_engedely_szam = st.text_input(L["hossz_engedely_szam"]) 
    hossz_engedely_ervenyes = st.text_input(L["hossz_engedely_ervenyes"], placeholder="YYYY-MM-DD")

    # Átvétel
    st.markdown(f"**{L['section_atvetel']}**")
    atvetel_mod_disp = st.selectbox(L["atvetel_mod"], options=[""] + ATVETEL_DISP, index=0)
    postai_cim_tipus_disp = st.selectbox(L["postai_cim_tipus"], options=[""] + POSTAI_DISP, index=0)

    # 4) Egészségbiztosítás
    st.markdown(f"**{L['section_egeszseg']}**")
    egeszseg_biztositas_disp = st.selectbox(L["egeszseg_biztositas"], options=[""] + YESNO_DISP, index=0)
    egeszseg_egyeb = st.text_input(L["egeszseg_egyeb"]) 

    # 5) Vissza-/továbbutazás
    st.markdown(f"**{L['section_visszaut']}**")
    visszaut_orszag = st.text_input(L["visszaut_orszag"]) 
    show_field_help("visszaut_orszag", ui_lang)
    kozlekedesi_eszkoz = st.text_input(L["kozlekedesi_eszkoz"]) 
    show_field_help("kozlekedesi_eszkoz", ui_lang)
    van_utlevel_disp = st.selectbox(L["van_utlevel"], options=[""] + YESNO_DISP, index=0)
    show_field_help("van_utlevel", ui_lang)
    van_vizum_disp = st.selectbox(L["van_vizum"], options=[""] + YESNO_DISP, index=0)
    show_field_help("van_vizum", ui_lang)
    van_menetjegy_disp = st.selectbox(L["van_menetjegy"], options=[""] + YESNO_DISP, index=0)
    show_field_help("van_menetjegy", ui_lang)
    van_anyagi_fedezet_disp = st.selectbox(L["van_anyagi_fedezet"], options=[""] + YESNO_DISP, index=0)
    show_field_help("van_anyagi_fedezet", ui_lang)
    fedezet_osszeg = st.text_input(L["fedezet_osszeg"]) 
    show_field_help("fedezet_osszeg", ui_lang)

   

    # 7) Egyéb adatok
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

    # 8) Kiskorú
    st.markdown(f"**{L['section_kiskoru']}**")
    kiskoru_utazik_disp = st.selectbox(L["kiskoru_utazik"], options=[""] + YESNO_DISP, index=0)

    # 9) Tervezett időtartam és cél
    st.markdown(f"**{L['section_tervezett']}**")
    tartozkodas_vege = st.text_input(L["tartozkodas_vege"], placeholder="YYYY-MM-DD")
    tartozkodas_celja_disp = st.selectbox(L["tartozkodas_celja"], options=[""] + CEL_DISP, index=0)

    # Fizetési tranzakció
    st.markdown(f"**{L['section_fizetes']}**")
    tranzakcio_szam = st.text_input(L["tranzakcio_szam"]) 

    # ====== HOZZÁTARTOZÓK – DINAMIKUS MEZŐK A FORMON BELÜL (HU/RU i18n) ======
    
    hozz = []
    
    # I18N listák
    ROKONSAG_HU = ["szülő", "gyermek", "házastárs", "testvér", "egyéb"]
    ROKONSAG_RU = ["родитель", "ребенок", "супруг(а)", "брат/сестра", "другое"]
    
    HOZZ_NEM_HU = ["férfi", "nő", "egyéb"]
    HOZZ_NEM_RU = ["мужской", "женский", "другое"]
    
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
            "tartozkodik_e": tartozkodas_e,
            "okmany_szam": okmany
        })

    # Sablonválasztás
    template_labels = [p.name for p in available_templates]
    defaults = [name for name in template_labels if name in DEFAULT_TEMPLATE_NAMES]
    selected_labels = st.multiselect(L["select_templates"], options=template_labels, default=defaults)

    submitted = st.form_submit_button(L["btn_generate"])



# =========================
# Beküldés feldolgozása
# =========================
if submitted:
    errors = []
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
    egeszseg_biztositas = to_canonical(ui_lang, "yesno", egeszseg_biztositas_disp)
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

    record = {
        # elérhetőség
        "phone": (phone or "").strip(),
        "email": (email or "").strip(),
        # személyes
        "vezeteknev": (vezeteknev or "").strip(),
        "keresztnev": (keresztnev or "").strip(),
        "szuletesi_csaladi": (szuletesi_csaladi or "").strip(),
        "szuletesi_uto": (szuletesi_uto or "").strip(),
        "anyja_csaladi": (anyja_csaladi or "").strip(),
        "anyja_uto": (anyja_uto or "").strip(),
        "nem": nem,
        "allampolgarsag": (allampolgarsag or "").strip(),
        "nemzetiseg": (nemzetiseg or "").strip(),
        "szuletesi_datum": (szuletesi_datum or "").strip(),
        "szuletesi_hely": (szuletesi_hely or "").strip(),
        "szuletesi_orszag": (szuletesi_orszag or "").strip(),
        "csaladi_allapot": csaladi_allapot,
        "vegzettseg": vegzettseg,
        "szakkepzettseg": (szakkepzettseg or "").strip(),
        "magyarorszagra_erkezese_elotti_foglalkozas": (elozo_foglalkozas or "").strip(),
        # útlevél
        "utlevel_szam": (utlevel_szam or "").strip(),
        "utlevel_kiadas": (utlevel_kiadas or "").strip(),
        "utlevel_helye": (utlevel_helye or "").strip(),
        "utlevel_tipus": utlevel_tipus,
        "utlevel_lejarat": (utlevel_lejarat or "").strip(),
        # szállás
        "helyrajzi_szam": (helyrajzi_szam or "").strip(),
        "iranyitoszam": (iranyitoszam or "").strip(),
        "telepules": (telepules or "").strip(),
        "kozterulet_nev": (kozterulet_nev or "").strip(),
        "kozterulet_jelleg": (kozterulet_jelleg or "").strip(),
        "hazszam": (hazszam or "").strip(),
        "epulet": (epulet or "").strip(),
        "lepcsohaz": (lepcsohaz or "").strip(),
        "emelet": (emelet or "").strip(),
        "ajto": (ajto or "").strip(),
        "szallas_jogcim": szallas_jogcim,
        # első/hosszabbítás
        "elso_beutazas_helye": (elso_beutazas_helye or "").strip(),
        "elso_beutazas_datuma": (elso_beutazas_datuma or "").strip(),
        "hossz_engedely_szam": (hossz_engedely_szam or "").strip(),
        "hossz_engedely_ervenyes": (hossz_engedely_ervenyes or "").strip(),
        # átvétel
        "atvetel_mod": atvetel_mod,
        "postai_cim_tipus": postai_cim_tipus,
        # egészség
        "egeszseg_biztositas": egeszseg_biztositas,
        "egeszseg_egyeb": (egeszseg_egyeb or "").strip(),
        # visszautazás
        "visszaut_orszag": (visszaut_orszag or "").strip(),
        "kozlekedesi_eszkoz": (kozlekedesi_eszkoz or "").strip(),
        "van_utlevel": van_utlevel,
        "van_vizum": van_vizum,
        "van_menetjegy": van_menetjegy,
        "van_anyagi_fedezet": van_anyagi_fedezet,
        "fedezet_osszeg": (fedezet_osszeg or "").strip(),
        # hozzátartozók
        "hozzatartozok_json": json.dumps(hozz, ensure_ascii=False),
        # egyéb adatok
        "elozo_orszag": (elozo_orszag or "").strip(),
        "elozo_telepules": (elozo_telepules or "").strip(),
        "elozo_cim": (elozo_cim or "").strip(),
        "mas_schengen_okmany": mas_schengen_okmany,
        "mas_schengen_tipus": (mas_schengen_tipus or "").strip(),
        "mas_schengen_szam": (mas_schengen_szam or "").strip(),
        "mas_schengen_ervenyes": (mas_schengen_ervenyes or "").strip(),
        "volt_elutasitas": volt_elutasitas,
        "volt_buntetve": volt_buntetve,
        "buntet_reszletek": (buntet_reszletek or "").strip(),
        "volt_kiutasitas": volt_kiutasitas,
        "kiutasitas_datum": (kiutasitas_datum or "").strip(),
        "fert_beteg": fert_beteg,
        "kap_ellatas": kap_ellatas,
        # kiskorú
        "kiskoru_utazik": kiskoru_utazik,
        # cél
        "tartozkodas_vege": (tartozkodas_vege or "").strip(),
        "tartozkodas_celja": tartozkodas_celja,
        # fizetés
        "tranzakcio_szam": (tranzakcio_szam or "").strip(),
        # összetett név (a fájlnevekhez)
        "teljes_nev": f"{(vezeteknev or '').strip()} {(keresztnev or '').strip()}".strip(),
    }

   
    # CIRILL SZÖVEG FORDÍTÁSA + TRANSLIT MINDIG (UI nyelvétől függetlenül)
    if True:

        # a) Foglalkozás
        job_val = record.get("magyarorszagra_erkezese_elotti_foglalkozas", "")
        if contains_cyrillic(job_val):
            hu_job = translator_translate_to_hungarian(job_val)
            record["magyarorszagra_erkezese_elotti_foglalkozas"] = hu_job or transliterate_to_latin(job_val)
        # b) Szakképzettség
        skill_val = record.get("szakkepzettseg", "")
        if contains_cyrillic(skill_val):
            hu_skill = translator_translate_to_hungarian(skill_val)
            record["szakkepzettseg"] = hu_skill or transliterate_to_latin(skill_val)
          # c) Születési hely
        birth_place = record.get("szuletesi_hely", "")
        if contains_cyrillic(birth_place):
            hu_birth_place = translator_translate_to_hungarian(birth_place)
            record["szuletesi_hely"] = hu_birth_place or transliterate_to_latin(birth_place)
    
        # d) Születési ország
        birth_country = record.get("szuletesi_orszag", "")
        if contains_cyrillic(birth_country):
            hu_birth_country = translator_translate_to_hungarian(birth_country)
            record["szuletesi_orszag"] = hu_birth_country or transliterate_to_latin(birth_country)
    
        # e) Nemzetiség
        nationality = record.get("nemzetiseg", "")
        if contains_cyrillic(nationality):
            hu_nationality = translator_translate_to_hungarian(nationality)
            record["nemzetiseg"] = hu_nationality or transliterate_to_latin(nationality)

        # f) Egyéb állampolgárság translit/fordítás
        allampolgarsag = record.get("allampolgarsag", "")
        if contains_cyrillic(allampolgarsag):
            hu_ap = translator_translate_to_hungarian(allampolgarsag)
            record["allampolgarsag"] = hu_ap or transliterate_to_latin(allampolgarsag)

        # g) Útlevél kiadási helye, ha Egyéb
        utlevel_helye = record.get("utlevel_helye", "")   
        if contains_cyrillic(utlevel_helye):
            hu_place = translator_translate_to_hungarian(utlevel_helye)
            record["utlevel_helye"] = hu_place or transliterate_to_latin(utlevel_helye)

        # h) Más shengeni okmány - Engedély típusa
        mas_schengen_tipus = record.get("mas_schengen_tipus", "")   
        if contains_cyrillic(mas_schengen_tipus):
            hu_mas_schengen_tipus = translator_translate_to_hungarian(mas_schengen_tipus)
            record["mas_schengen_tipus"] = hu_mas_schengen_tipus or transliterate_to_latin(mas_schengen_tipus)       
         
        # i) Teljes körű egészségbiztosítás Egyéb megjegyzés
        egeszseg_egyeb = record.get("egeszseg_egyeb", "")
        if contains_cyrillic(egeszseg_egyeb):
            hu_egeszs = translator_translate_to_hungarian(egeszseg_egyeb)
            record["egeszseg_egyeb"] = hu_egeszs or transliterate_to_latin(egeszseg_egyeb)
        
        # j) Visszautazás országa és közlekedési eszköz
        visszaut_orszag = record.get("visszaut_orszag", "")
        if contains_cyrillic(visszaut_orszag):
            hu_visszaut_orszag = translator_translate_to_hungarian(visszaut_orszag)
            record["visszaut_orszag"] = hu_visszaut_orszag or transliterate_to_latin(visszaut_orszag)

        kozlekedesi_eszkoz = record.get("kozlekedesi_eszkoz", "")
        if contains_cyrillic(kozlekedesi_eszkoz):
            hu_kozlekedesi_eszkoz = translator_translate_to_hungarian(kozlekedesi_eszkoz)
            record["kozlekedesi_eszkoz"] = hu_kozlekedesi_eszkoz or transliterate_to_latin(kozlekedesi_eszkoz)
            
        # k) Mo-ra érkezés előtti ország
        elozo_orszag = record.get("elozo_orszag", "")
        if contains_cyrillic(elozo_orszag):
            hu_elozo_orszag = translator_translate_to_hungarian(elozo_orszag)
            record["elozo_orszag"] = hu_elozo_orszag or transliterate_to_latin(elozo_orszag)

        # l) Bűncselekmény részletei
        buntet_reszletek = record.get("buntet_reszletek", "")
        if contains_cyrillic(buntet_reszletek):
            hu_buntet_reszletek = translator_translate_to_hungarian(buntet_reszletek)
            record["buntet_reszletek"] = hu_buntet_reszletek or transliterate_to_latin(buntet_reszletek)
            
        # m) Minden egyéb mező transliterációja
        to_trans = [
            "phone","email","vezeteknev","keresztnev","szuletesi_csaladi","szuletesi_uto",
            "anyja_csaladi","anyja_uto","allampolgarsag","nemzetiseg","szuletesi_hely","szuletesi_orszag",
            "utlevel_szam","utlevel_helye","helyrajzi_szam","iranyitoszam","telepules","kozterulet_nev",
            "kozterulet_jelleg","hazszam","epulet","lepcsohaz","emelet","ajto","elso_beutazas_helye",
            "fedezet_osszeg","elozo_telepules","elozo_cim","mas_schengen_szam","buntet_reszletek",
            "tranzakcio_szam"
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

    # Validáció + dátumnormalizálás
    errors.extend(validate_record(record, L, ui_lang))

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
    # Kontakt
    "phone","email",
    # Személyes
    "vezeteknev","keresztnev","szuletesi_csaladi","szuletesi_uto","anyja_csaladi","anyja_uto",
    "nem","allampolgarsag","nemzetiseg","csaladi_allapot","szuletesi_datum","szuletesi_hely","szuletesi_orszag",
    "vegzettseg","szakkepzettseg","magyarorszagra_erkezese_elotti_foglalkozas",
    # Útlevél
    "utlevel_szam","utlevel_kiadas","utlevel_helye","utlevel_tipus","utlevel_lejarat",
    # Szállás
    "helyrajzi_szam","iranyitoszam","telepules","kozterulet_nev","kozterulet_jelleg","hazszam","epulet","lepcsohaz","emelet","ajto","szallas_jogcim",
    # Első/hosszabbítás
    "elso_beutazas_helye","elso_beutazas_datuma","hossz_engedely_szam","hossz_engedely_ervenyes",
    # Átvétel
    "atvetel_mod","postai_cim_tipus",
    # Egészség
    "egeszseg_biztositas","egeszseg_egyeb",
    # Visszautazás
    "visszaut_orszag","kozlekedesi_eszkoz","van_utlevel","van_vizum","van_menetjegy","van_anyagi_fedezet","fedezet_osszeg",
    # Hozzátartozók – JSON
    "hozzatartozok_json",
    # Egyéb
    "elozo_orszag","elozo_telepules","elozo_cim",
    "mas_schengen_okmany","mas_schengen_tipus","mas_schengen_szam","mas_schengen_ervenyes",
    "volt_elutasitas","volt_buntetve","buntet_reszletek","volt_kiutasitas","kiutasitas_datum","fert_beteg","kap_ellatas",
    # Kiskorú
    "kiskoru_utazik",
    # Cél
    "tartozkodas_vege","tartozkodas_celja",
    # Fizetés
    "tranzakcio_szam",
    # Egyes sablonokhoz hasznos
    "teljes_nev",
]

with st.expander("📌 Helyőrzők (templates) – kattintson a listához", expanded=False):
    st.code("\n".join(PLACEHOLDERS), language="text")
