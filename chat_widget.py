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


# # =========================================================
# 6) TELJES, HIBAMENTES, KATTINTHATÓ MESSENGER CHAT
# =========================================================

def floating_chat():

    # ------------------------------
    # STATE
    # ------------------------------
    if "chat_open" not in st.session_state:
        st.session_state.chat_open = False

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []


    # ------------------------------
    # FIXED OVERLAY HTML + CSS
    # ------------------------------
    st.markdown("""
    <style>
        /* ROOT: always fixed to bottom-right */
        #chat-root {
            position: fixed;
            bottom: 0;
            right: 0;
            z-index: 999999;
            pointer-events: none; /* background passive */
        }

        /* BUBBLE always clickable */
        .chat-bubble, .chat-bubble * {
            pointer-events: auto;
        }

        .chat-bubble {
            position: absolute;
            bottom: 24px;
            right: 24px;
        }

        .chat-bubble button {
            width: 80px;
            height: 80px;
            border-radius: 50%;
            font-size: 40px;
            border: none;
            background: #0084FF;
            color: white;
            cursor: pointer;
            box-shadow: 0 6px 20px rgba(0,0,0,0.25);
        }

        /* PANEL */
        .chat-panel, .chat-panel * {
            pointer-events: auto;
        }

        .chat-panel {
            position: absolute;
            bottom: 120px;
            right: 24px;
            width: 380px;
            height: 520px;
            background: white;
            border-radius: 16px;
            padding: 14px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.25);
            display: flex;
            flex-direction: column;
        }

        .chat-scroll {
            flex-grow: 1;
            overflow-y: auto;
            padding-right: 10px;
        }

        .bubble-user {
            background: #0084ff;
            color: white;
            padding: 10px 14px;
            border-radius: 16px;
            margin-left: auto;
            margin-bottom: 8px;
            max-width: 80%;
        }

        .bubble-ai {
            background: #e5e5ea;
            color: #111;
            padding: 10px 14px;
            border-radius: 16px;
            margin-right: auto;
            margin-bottom: 8px;
            max-width: 80%;
        }
    </style>

    <!-- FIXED ROOT -->
    <div id="chat-root">

        <!-- BUBBLE -->
        <div class="chat-bubble">
            <button onclick="
                [...window.parent.document.querySelectorAll('[data-testid=\\'chat_toggle_btn\\']')]
                .forEach(btn => btn.click());
            ">💬</button>
        </div>

    </div>
    """, unsafe_allow_html=True)


    # ------------------------------------------------------
    # INVISIBLE STREAMLIT BUTTON FOR TOGGLING CHAT PANEL
    # ------------------------------------------------------
    toggle_pressed = st.button("toggle", key="chat_toggle_btn", help="hidden-toggle", type="secondary")
    if toggle_pressed:
        st.session_state.chat_open = not st.session_state.chat_open


    # ------------------------------------------------------
    # RENDER CHAT PANEL IF OPEN
    # ------------------------------------------------------
    if not st.session_state.chat_open:
        return

    panel = st.container()
    with panel:

        st.markdown('<div class="chat-panel">', unsafe_allow_html=True)

        # --------- CHAT HISTORY ----------
        st.markdown('<div class="chat-scroll">', unsafe_allow_html=True)

        for role, text in st.session_state.chat_messages:
            css = "bubble-user" if role == "user" else "bubble-ai"
            st.markdown(f'<div class="{css}">{text}</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

        # --------- INPUT ----------
        inp = st.text_input("Írj üzenetet…", key="chat_input_text", label_visibility="collapsed")
        if inp:
            # user message
            st.session_state.chat_messages.append(("user", inp))

            # AI answer
            ans = generate_response(inp, st.session_state.get("ui_lang", "hu"))
            st.session_state.chat_messages.append(("assistant", ans))

            # clear input
            st.session_state.chat_input_text = ""

        st.markdown("</div>", unsafe_allow_html=True)
