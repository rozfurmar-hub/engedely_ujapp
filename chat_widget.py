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

    # ===== 0) Streamlit default chatpanel elrejtése (fontos!) =====
    st.markdown("""
    <style>
        /* Rejtsük el a Streamlit saját chat-keretét */
        [data-testid="stChat"] {
            display: none !important;
        }
    </style>
    """, unsafe_allow_html=True)

    # ===== 1) Chat ablak állapot =====
    if "messenger_open" not in st.session_state:
        st.session_state.messenger_open = False

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # ===== 2) Messenger-stílusú CSS =====
    st.markdown("""
    <style>
        /* Lebegő buborék */
        .floating-chat-btn {
            position: fixed !important;
            bottom: 26px !important;
            right: 26px !important;
            z-index: 99999 !important;
        }
        .floating-chat-btn button {
            width: 80px !important;
            height: 80px !important;
            font-size: 42px !important;
            border-radius: 50% !important;
            background: #0084ff !important;
            color: white !important;
            border: none !important;
            box-shadow: 0 6px 16px rgba(0,0,0,0.25) !important;
        }

        /* Messenger panel */
        .messenger-panel {
            position: fixed !important;
            bottom: 120px !important;
            right: 26px !important;
            width: 380px !important;
            height: 520px !important;
            background: white !important;
            border-radius: 16px !important;
            box-shadow: 0 8px 24px rgba(0,0,0,0.30) !important;
            z-index: 99998 !important;
            padding: 14px !important;
            display: flex !important;
            flex-direction: column !important;
        }

        /* Scroll area */
        .chat-scroll {
            flex-grow: 1 !important;
            overflow-y: auto !important;
            padding-right: 6px !important;
        }

        /* Üzenet buborékok */
        .bubble-user {
            background: #0084ff !important;
            color: white !important;
            padding: 10px 14px !important;
            border-radius: 16px !important;
            max-width: 80% !important;
            margin-left: auto !important;
            margin-bottom: 8px !important;
        }
        .bubble-ai {
            background: #e5e5ea !important;
            color: #111 !important;
            padding: 10px 14px !important;
            border-radius: 16px !important;
            max-width: 80% !important;
            margin-right: auto !important;
            margin-bottom: 8px !important;
        }
    </style>
    """, unsafe_allow_html=True)

    # ===== 3) Lebegő buborék gomb =====
    btn_holder = st.empty()
    with btn_holder.container():
        if st.button("💬", key="messenger_btn"):
            st.session_state.messenger_open = not st.session_state.messenger_open

        # CSS osztály hozzárendelése a gombhoz
        st.markdown("""
        <script>
        const btn = window.parent.document.querySelector('button[data-testid="messenger_btn"]');
        if (btn) btn.parentElement.classList.add("floating-chat-btn");
        </script>
        """, unsafe_allow_html=True)

    # Ha a chatablak zárva van → vége
    if not st.session_state.messenger_open:
        return

    # ===== 4) A lebegő panel megjelenítése =====
    panel = st.empty()

    with panel.container():
        st.markdown('<div class="messenger-panel">', unsafe_allow_html=True)

        # Scroll tartalom
        st.markdown('<div class="chat-scroll">', unsafe_allow_html=True)

        # Üzenetek kirajzolása
        for role, msg in st.session_state.chat_history:
            if role == "user":
                st.markdown(
                    f'<div class="bubble-user">{msg}</div>',
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f'<div class="bubble-ai">{msg}</div>',
                    unsafe_allow_html=True
                )

        st.markdown('</div>', unsafe_allow_html=True)

        # ===== 5) Üzenet küldése =====
        user_msg = st.chat_input("Írja ide üzenetét…")

        if user_msg:
            st.session_state.chat_history.append(("user", user_msg))
            answer = generate_response(
                user_msg,
                st.session_state.get("ui_lang", "hu")
            )
            st.session_state.chat_history.append(("assistant", answer))

        st.markdown('</div>', unsafe_allow_html=True)
