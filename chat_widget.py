import streamlit as st
import uuid
import openai
from field_help import load_field_help


# =========================================================
# 1) Tudásbázis kereső
# =========================================================
def get_kb_answer(question: str, ui_lang: str):
    kb = load_field_help(ui_lang)
    q = question.lower()
    for key, info in kb.items():
        if key.lower() in q:
            return f"**{info.get('label','')}**\n\n{info.get('help','')}"
    return None


# =========================================================
# 2) Nyelvfelismerés a kérdésből
# =========================================================
def detect_lang(text: str):
    # nagyon egyszerű: cirill = RU, különben HU
    for c in text:
        if "\u0400" <= c <= "\u04FF":
            return "ru"
    return "hu"


# =========================================================
# 3) AI fallback
# =========================================================
def ask_ai(question, ui_lang):
    # automatikus felülírás: ha RU kérdést írtak → ruszki választ kérünk
    detected = detect_lang(question)
    ui_lang = detected

    client = openai.OpenAI(api_key=st.secrets["openai"]["api_key"])

    system_prompt_hu = (
        "Segítőkész magyar ügyintéző asszisztens vagy. "
        "Rövid, világos, barátságos válaszokat adsz."
    )

    system_prompt_ru = (
        "Вы — дружелюбный помощник. "
        "Отвечайте коротко и понятно, на русском языке."
    )

    system_prompt = system_prompt_hu if ui_lang == "hu" else system_prompt_ru

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question}
        ],
        max_tokens=400
    )

    return response.choices[0].message.content


# =========================================================
# 4) Tudásbázis → AI válaszoló logika
# =========================================================
def generate_response(question, ui_lang):
    kb_answer = get_kb_answer(question, ui_lang)
    if kb_answer:
        return kb_answer
    return ask_ai(question, ui_lang)


# =========================================================
# 5) Chat UI
# =========================================================
def render_chat_ai():
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    ui_lang = st.session_state.get("ui_lang", "hu")

    # chat előzmények kiírása
    for role, msg in st.session_state.chat_history:
        st.chat_message(role).write(msg)

    # új kérdés
    question = st.chat_input("Írja ide kérdését… / Введите свой вопрос…")
    if question:
        st.session_state.chat_history.append(("user", question))
        answer = generate_response(question, ui_lang)
        st.session_state.chat_history.append(("assistant", answer))
        st.chat_message("assistant").write(answer)


# =========================================================
# 6) TELJES MESSENGER-SZERŰ LEBEGŐ CHAT – VÉGLEGES VERZIÓ
# =========================================================

def floating_chat():

    # state
    if "chat_open" not in st.session_state:
        st.session_state.chat_open = False
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # CSS
    st.markdown("""
    <style>
        .chat-button {
            position: fixed;
            bottom: 24px;
            right: 24px;
            z-index: 99998;
        }
        .chat-button button {
            width: 75px !important;
            height: 75px !important;
            border-radius: 50% !important;
            background: #0084ff !important;
            color: white !important;
            font-size: 38px !important;
            border: none !important;
            box-shadow: 0 5px 15px rgba(0,0,0,0.25);
        }

        .chat-panel {
            position: fixed;
            bottom: 120px;
            right: 24px;
            width: 380px;
            height: 520px;
            z-index: 99997;
            background: white;
            border-radius: 16px;
            padding: 14px;
            display: flex;
            flex-direction: column;
            box-shadow: 0 8px 24px rgba(0,0,0,0.25);
        }

        .chat-scroll {
            flex-grow: 1;
            overflow-y: auto;
            padding-right: 6px;
        }

        .bubble-user {
            background: #0084ff;
            color: white;
            padding: 10px 14px;
            margin-bottom: 8px;
            max-width: 80%;
            border-radius: 16px;
            margin-left: auto;
        }

        .bubble-ai {
            background: #e5e5ea;
            color: #111;
            padding: 10px 14px;
            margin-bottom: 8px;
            max-width: 80%;
            border-radius: 16px;
            margin-right: auto;
        }
    </style>
    """, unsafe_allow_html=True)


    # --- FIX, statikus konténer a gombnak ---
    bubble_container = st.container()
    with bubble_container:
        st.markdown('<div class="chat-button">', unsafe_allow_html=True)
        if st.button("💬", key="msg_btn"):
            st.session_state.chat_open = not st.session_state.chat_open
        st.markdown('</div>', unsafe_allow_html=True)

    # --- Panel megjelenítése ---
    if not st.session_state.chat_open:
        return

    panel_container = st.container()
    with panel_container:
        st.markdown('<div class="chat-panel">', unsafe_allow_html=True)

        st.markdown('<div class="chat-scroll">', unsafe_allow_html=True)
        for role, msg in st.session_state.chat_messages:
            if role == "user":
                st.markdown(f'<div class="bubble-user">{msg}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="bubble-ai">{msg}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        msg = st.text_input("Írj üzenetet…", key="msg_input", label_visibility="collapsed")
        if msg:
            st.session_state.chat_messages.append(("user", msg))
            answer = generate_response(msg, st.session_state.get("ui_lang", "hu"))
            st.session_state.chat_messages.append(("assistant", answer))
            st.session_state.msg_input = ""

        st.markdown('</div>', unsafe_allow_html=True)
