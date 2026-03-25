import streamlit as st
import openai
import unicodedata
from field_help import load_field_help


# =========================================================
# Tudásbázis kulcs-normalizáló függvény
# =========================================================
def normalize(s: str) -> str:
    """
    Kisbetű, ékezetek eltávolítása, nem alfanumerikus karakterek törlése.
    Így: 'tranzakció szám' -> 'tranzakcioszam'
    """
    if not s:
        return ""

    s = s.lower()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != "Mn")
    s = ''.join(c for c in s if c.isalnum())
    return s


# =========================================================
# Tudásbázis kereső (javított)
# =========================================================
def get_kb_answer(question: str, ui_lang: str):
    kb = load_field_help(ui_lang)
    q = normalize(question)

    for key, info in kb.items():
        k = normalize(key)
        if k in q:
            return f"**{info['label']}**\n\n{info['help']}"

    return None


# =========================================================
# Nyelvfelismerés
# =========================================================
def detect_lang(text: str):
    for c in text:
        if "\u0400" <= c <= "\u04FF":
            return "ru"
    return "hu"


# =========================================================
# AI fallback (csak ha NINCS tudásbázis találat)
# =========================================================
def ask_ai(question, ui_lang):
    detected = detect_lang(question)
    ui_lang = detected

    client = openai.OpenAI(api_key=st.secrets["openai"]["api_key"])

    system_prompt_hu = (
        "Segítőkész magyar ügyintéző vagy. "
        "Csak az adatlap kitöltésével kapcsolatos kérdésekre válaszolj. "
        "Ha a kérdés nem kapcsolódik az űrlaphoz, tereld vissza udvariasan."
    )

    system_prompt_ru = (
        "Вы — вежливый помощник. "
        "Отвечайте только на вопросы, связанные с заполнением формы. "
        "Если вопрос не по теме, мягко верните пользователя к заполнению формы."
    )

    system_prompt = system_prompt_hu if ui_lang == "hu" else system_prompt_ru

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        max_tokens=300,
    )

    return response.choices[0].message.content


# =========================================================
# Tudásbázis → vagy AI fallback
# =========================================================
def generate_response(question, ui_lang):
    kb_answer = get_kb_answer(question, ui_lang)
    if kb_answer:
        return kb_answer
    return ask_ai(question, ui_lang)


# =========================================================
# Messenger-szerű lebegő chat
# =========================================================
def floating_chat():

    # ------ STATE inicializálása ------
    if "chat_open" not in st.session_state:
        st.session_state.chat_open = False

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # új: input mező egyedi kulcs számlálója
    if "chat_input_key" not in st.session_state:
        st.session_state.chat_input_key = 0

    # ------ CHAT TOGGLE GOMB ------
    toggled = st.button("CHAT", key="chat_toggle_btn")

    if toggled:
        st.session_state.chat_open = not st.session_state.chat_open

    if not st.session_state.chat_open:
        return  # panel nem látszik, kilépünk

    # ------ CHAT PANEL ------
    panel = st.container()

    with panel:
        st.markdown('<div class="chat-panel">', unsafe_allow_html=True)

        # --- scroll ---
        st.markdown('<div class="chat-scroll">', unsafe_allow_html=True)

        if not st.session_state.chat_messages:
            st.markdown(
                '<div style="opacity:0.6; padding:10px;">'
                'Tegye fel kérdését! / Задайте вопрос!'
                '</div>',
                unsafe_allow_html=True
            )
        else:
            # meglévő üzenetek kirajzolása
            for role, txt in st.session_state.chat_messages:
                css = "bubble-user" if role == "user" else "bubble-ai"
                st.markdown(f'<div class="{css}">{txt}</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

        # ------ CHAT INPUT MEZŐ ------
        user_msg = st.text_input(
            "",
            key=f"chat_input_{st.session_state.chat_input_key}",
            placeholder="Tegye fel kérdését! / Задайте вопрос!"
        )

        # ------ ÜZENET BEKÜLDÉSE ------
        if user_msg:
            # felhasználó üzenete
            st.session_state.chat_messages.append(("user", user_msg))
            # AI vagy tudásbázis válasza
            ai = generate_response(user_msg, st.session_state.get("ui_lang", "hu"))
            st.session_state.chat_messages.append(("assistant", ai))

            # új input mező kulcsa (hogy üres legyen)
            st.session_state.chat_input_key += 1

            # teljes újrarender – AZONNAL megjelenik a válasz
            st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)
