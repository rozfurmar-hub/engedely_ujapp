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
    # Nyitott / csukott állapot
    if "messenger_open" not in st.session_state:
        st.session_state.messenger_open = False

    # ===== CSS: Messenger stílus =====
    st.markdown("""
    <style>

    .messenger-button {
        position: fixed;
        bottom: 22px;
        right: 22px;
        background: #0084ff;
        color: white;
        width: 64px;
        height: 64px;
        border-radius: 50%;
        text-align: center;
        font-size: 32px;
        line-height: 64px;
        cursor: pointer;
        z-index: 10000;
        box-shadow: 0 4px 12px rgba(0,0,0,0.25);
    }

    .messenger-panel {
        position: fixed;
        bottom: 100px;
        right: 22px;
        width: 360px;
        height: 520px;
        background: white;
        border-radius: 14px;
        box-shadow: 0 6px 20px rgba(0,0,0,0.25);
        z-index: 10001;
        display: flex;
        flex-direction: column;
        overflow: hidden;
        animation: fadeIn 0.25s ease-out;
    }

    @keyframes fadeIn {
        from {opacity: 0; transform: translateY(10px);}
        to {opacity: 1; transform: translateY(0);}
    }

    .chat-scroll {
        padding: 12px;
        overflow-y: auto;
        flex-grow: 1;
        background: #f4f5f7;
    }

    .bubble-user {
        background: #0084ff;
        padding: 10px 14px;
        color: white;
        border-radius: 16px;
        margin-bottom: 10px;
        max-width: 80%;
        align-self: flex-end;
        border-bottom-right-radius: 4px;
    }
    .bubble-ai {
        background: #e8e8ea;
        padding: 10px 14px;
        color: #222;
        border-radius: 16px;
        margin-bottom: 10px;
        max-width: 80%;
        align-self: flex-start;
        border-bottom-left-radius: 4px;
    }

    </style>
    """, unsafe_allow_html=True)

    # ====== Lebegő gomb ======
    btn_col = st.empty()
    with btn_col:
        # Streamlit button
        if st.button("💬", key="messenger_btn", help="Üzenet küldése"):
            st.session_state.messenger_open = not st.session_state.messenger_open

        # Pozicionálás CSS-sel
        st.markdown("""
            <script>
            var btn = window.parent.document.querySelector('[data-testid="stButton"]');
            if (btn) { btn.parentElement.classList.add('messenger-button'); }
            </script>
        """, unsafe_allow_html=True)

    # ====== Ha zárva van, kilépünk ======
    if not st.session_state.messenger_open:
        return

    # ===== Panel =====
    panel = st.container()
    with panel:
        st.markdown('<div class="messenger-panel">', unsafe_allow_html=True)

        # Chat történet megjelenítése
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        st.markdown('<div class="chat-scroll">', unsafe_allow_html=True)
        for role, msg in st.session_state.chat_history:
            if role == "user":
                st.markdown(f'<div class="bubble-user">{msg}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="bubble-ai">{msg}</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        # Üzenet mező
        user_msg = st.chat_input("Írj üzenetet…")

        if user_msg:
            st.session_state.chat_history.append(("user", user_msg))
            answer = generate_response(user_msg, st.session_state.get("ui_lang", "hu"))
            st.session_state.chat_history.append(("assistant", answer))

        st.markdown("</div>", unsafe_allow_html=True)
