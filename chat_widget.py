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
    # Chat panel állapot
    if "messenger_open" not in st.session_state:
        st.session_state.messenger_open = False

    # ======== Messenger-szerű CSS ========
    st.markdown("""
    <style>

    /* Messenger gomb */
    .messenger-button {
        position: fixed;
        bottom: 22px;
        right: 22px;
        background: #0084FF;
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

    /* Felugró panel */
    .messenger-panel {
        position: fixed;
        bottom: 100px;
        right: 22px;
        width: 360px;
        height: 520px;
        background: #ffffff;
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

    /* Chat scroll area */
    .chat-scroll {
        padding: 12px;
        overflow-y: auto;
        flex-grow: 1;
        background: #f4f5f7;
    }

    /* Üzenet buborékok */
    .bubble-user {
        background: #0084FF;
        padding: 10px 14px;
        color: white;
        border-radius: 16px;
        margin-bottom: 10px;
        max-width: 80%;
        align-self: flex-end;
        border-bottom-right-radius: 4px;
    }
    .bubble-ai {
        background: #E8E8EA;
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

    # ======== Lebegő gomb Streamlit alatt ========
    btn_container = st.container()
    with btn_container:
        st.markdown('<div class="messenger-button" onclick="toggleMessenger()">💬</div>',
                    unsafe_allow_html=True)

    # ======== Javascript toggle ========
    st.markdown("""
    <script>
        function toggleMessenger() {
            fetch('/_stcore/messenger_toggle', {method: 'POST'});
        }
    </script>
    """, unsafe_allow_html=True)

    # ========= Rejtett API hívás Streamlithez =========
    # Streamlit hack: server_request → session_state toggle
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    from streamlit.web.server.websocket_headers import ServerNotInitialized

    try:
        ctx = get_script_run_ctx()
        if ctx and ctx.request and ctx.request.path == "/_stcore/messenger_toggle":
            st.session_state.messenger_open = not st.session_state.messenger_open
    except ServerNotInitialized:
        pass

    # ========= Panel megjelenítése =========
    if not st.session_state.messenger_open:
        return

    panel = st.container()
    with panel:
        st.markdown('<div class="messenger-panel">', unsafe_allow_html=True)

        # Belül: chat scroll area
        st.markdown('<div class="chat-scroll">', unsafe_allow_html=True)

        # CHAT KIÍRÁSA MESSENGER-BUBORÉKOKKAL
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        for role, msg in st.session_state.chat_history:
            if role == "user":
                st.markdown(f'<div class="bubble-user">{msg}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="bubble-ai">{msg}</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

        # Üzenet írás mező
        user_msg = st.chat_input("Írj üzenetet…")
        if user_msg:
            st.session_state.chat_history.append(("user", user_msg))
            answer = generate_response(user_msg, st.session_state.get("ui_lang", "hu"))
            st.session_state.chat_history.append(("assistant", answer))

        st.markdown('</div>', unsafe_allow_html=True)
