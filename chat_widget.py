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
# 6) Lebegő buborék PANEL — végre helyesen
# =========================================================
def floating_chat():

    # --- Panel megnyitása / bezárása ---
    if "messenger_open" not in st.session_state:
        st.session_state.messenger_open = False

    # --- CSS a Messenger stílushoz ---
    st.markdown("""
    <style>
        .floating-button {
            position: fixed;
            bottom: 22px;
            right: 22px;
            z-index: 9999;
            border-radius: 50%;
        }

        .messenger-panel {
            position: fixed;
            bottom: 100px;
            right: 22px;
            width: 360px;
            height: 480px;
            background: white;
            border-radius: 14px;
            box-shadow: 0 6px 20px rgba(0,0,0,0.25);
            z-index: 9998;
            padding: 12px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
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
            border-radius: 16px;
            max-width: 80%;
            align-self: flex-end;
            margin-bottom: 8px;
        }

        .bubble-ai {
            background: #e5e5ea;
            color: #222;
            padding: 10px 14px;
            border-radius: 16px;
            max-width: 80%;
            align-self: flex-start;
            margin-bottom: 8px;
        }
    </style>
    """, unsafe_allow_html=True)

    # --- Lebegő buborék gomb ---
    button_placeholder = st.empty()
    with button_placeholder.container():
        if st.button("💬", key="chat_open_btn"):
            st.session_state.messenger_open = not st.session_state.messenger_open

        # Buborék pozicionálása CSS-sel
        st.markdown("""
            <script>
                const btn = window.parent.document.querySelector('[data-testid="chat_open_btn"]');
                if (btn) btn.parentElement.classList.add("floating-button");
            </script>
        """, unsafe_allow_html=True)

    # --- Ha zárva van, kilépünk ---
    if not st.session_state.messenger_open:
        return

    # --- Lebegő chatpanel ---
    panel = st.empty()
    with panel.container():
        st.markdown('<div class="messenger-panel">', unsafe_allow_html=True)

        # Chat tartalom
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        st.markdown('<div class="chat-scroll">', unsafe_allow_html=True)

        for role, msg in st.session_state.chat_history:
            if role == "user":
                st.markdown(f'<div class="bubble-user">{msg}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="bubble-ai">{msg}</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

        # Chat input
        user_msg = st.chat_input("Írj üzenetet…")
        if user_msg:
            st.session_state.chat_history.append(("user", user_msg))
            answer = generate_response(user_msg, st.session_state.get("ui_lang", "hu"))
            st.session_state.chat_history.append(("assistant", answer))

        st.markdown('</div>', unsafe_allow_html=True)
