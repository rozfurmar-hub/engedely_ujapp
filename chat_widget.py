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

    # --- Init state ---
    if "messenger_open" not in st.session_state:
        st.session_state.messenger_open = False

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []   # (role, text)

    # --- CSS ---
    st.markdown("""
    <style>

    /* Lebegő gomb */
    .chat-bubble {
        position: fixed;
        bottom: 26px;
        right: 26px;
        z-index: 99998;
    }
    .chat-bubble button {
        width: 80px !important;
        height: 80px !important;
        font-size: 42px !important;
        border-radius: 50% !important;
        background: #0084ff !important;
        color: white !important;
        border: none !important;
        box-shadow: 0 6px 16px rgba(0,0,0,0.25);
    }

    /* Chat panel */
    .chat-panel {
        position: fixed;
        bottom: 120px;
        right: 26px;
        width: 380px;
        height: 520px;
        background: white;
        border-radius: 16px;
        padding: 14px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.30);
        z-index: 99997;
        display: flex;
        flex-direction: column;
    }

    /* Scroll */
    .chat-scroll {
        flex-grow: 1;
        overflow-y: auto;
        padding-right: 8px;
    }

    /* Bubbles */
    .bubble-user {
        background: #0084ff;
        color: white;
        padding: 10px 14px;
        border-radius: 16px;
        max-width: 80%;
        margin-left: auto;
        margin-bottom: 8px;
    }
    .bubble-ai {
        background: #e5e5ea;
        color: #111;
        padding: 10px 14px;
        border-radius: 16px;
        max-width: 80%;
        margin-right: auto;
        margin-bottom: 8px;
    }

    </style>
    """, unsafe_allow_html=True)

    # --- Bubble button ---
    btn = st.empty()
    with btn.container():
        if st.button("💬", key="open_msg_btn"):
            st.session_state.messenger_open = not st.session_state.messenger_open

        st.markdown("""
        <script>
        const btn = window.parent.document.querySelector('button[data-testid="open_msg_btn"]');
        if (btn) btn.parentElement.classList.add("chat-bubble");
        </script>
        """, unsafe_allow_html=True)

    # If closed → exit
    if not st.session_state.messenger_open:
        return

    # --- Chat panel ---
    panel = st.empty()
    with panel.container():
        st.markdown('<div class="chat-panel">', unsafe_allow_html=True)

        st.markdown('<div class="chat-scroll">', unsafe_allow_html=True)

        # Bubbles
        for role, text in st.session_state.chat_messages:
            if role == "user":
                st.markdown(f'<div class="bubble-user">{text}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="bubble-ai">{text}</div>', unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        # --- Input field ---
        user_msg = st.text_input(
            "Írj üzenetet…",
            key="msg_input",
            label_visibility="collapsed",
            placeholder="Írd be az üzeneted…"
        )

        if user_msg:
            # add user msg
            st.session_state.chat_messages.append(("user", user_msg))

            # generate AI answer
            ai = generate_response(
                user_msg,
                st.session_state.get("ui_lang", "hu")
            )
            st.session_state.chat_messages.append(("assistant", ai))

            # clear input
            st.session_state.pop("msg_input", None)
        st.markdown("</div>", unsafe_allow_html=True)
