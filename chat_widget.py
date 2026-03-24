import streamlit as st
import openai
from field }from field_help import load_field_help

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

    /* Hidden toggle button (but JS-clickable) */
    button[data-testid="chat_toggle_btn"] {
        opacity: 0 !important;
        width: 1px !important;
        height: 1px !important;
        padding: 0 !important;
        margin: 0 !important;
        border: none !important;
        background: transparent !important;
        color: transparent !important;
        pointer-events: none !important;
    }

</style>

<div id="chat-root">
    <div class="chat-bubble">
        <button onclick="
            [...window.parent.document.querySelectorAll('[data-testid=\\'chat_toggle_btn\\']')]
            .forEach(btn => btn.click());
        ">💬</button>
    </div>
</div>

""", unsafe_allow_html=True)

    # Hidden toggle target
    toggled = st.button("toggle", key="chat_toggle_btn")
    if toggled:
        st.session_state.chat_open = not st.session_state.chat_open

    if not st.session_state.chat_open:
        return

    # PANEL
    panel = st.container()
    with panel:

        st.markdown('<div class="chat-panel">', unsafe_allow_html=True)

        st.markdown('<div class="chat-scroll">', unsafe_allow_html=True)
        for role, msg in st.session_state.chat_messages:
            css = "bubble-user" if role == "user" else "bubble-ai"
            st.markdown(f'<div class="{css}">{msg}</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        user_msg = st.text_input("Írj üzenetet…", key="chat_input_text", label_visibility="collapsed")
        if user_msg:
            st.session_state.chat_messages.append(("user", user_msg))
            ai = generate_response(user_msg, st.session_state.get("ui_lang", "hu"))
            st.session_state.chat_messages.append(("assistant", ai))
            st.session_state.chat_input_text = ""

        st.markdown("</div>", unsafe_allow_html=True)

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
# 2) Nyelvfelismerés
# =========================================================
def detect_lang(text: str):
    for c in text:
        if "\u0400" <= c <= "\u04FF":
            return "ru"
    return "hu"

# =========================================================
# 3) AI fallback
# =========================================================
def ask_ai(question, ui_lang):
    detected = detect_lang(question)
    ui_lang = detected

    client = openai.OpenAI(api_key=st.secrets["openai"]["api_key"])

    system_prompt_hu = (
        "Segítőkész magyar ügyintéző asszisztens vagy. "
        "Rövid, világos, barátságos válaszokat adsz."
    )
    system_prompt_ru = (
        "Вы — дружелюбный помощник. "
        "Отвечайте коротко и понятно, na вашем языке."
    )

    system_prompt = system_prompt_hu if ui_lang == "hu" else system_prompt_ru

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        max_tokens=400,
    )

    return response.choices[0].message.content

# =========================================================
# 4) Tudásbázis → AI válasz
# =========================================================
def generate_response(question, ui_lang):
    kb_answer = get_kb_answer(question, ui_lang)
    if kb_answer:
        return kb_answer
    return ask_ai(question, ui_lang)

# =========================================================
# 5) Messenger-szerű lebegő chat – VÉGLEGES, MŰKÖDŐ VERZIÓ
# =========================================================
def floating_chat():

    # ---- init state ----
    if "chat_open" not in st.session_state:
        st.session_state.chat_open = False

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # ======================================================
    # FIX OVERLAY + CSS
    # ======================================================
    st.markdown("""
<style>

    /* ROOT LAYER */
    #chat-root {
        position: fixed;
        bottom: 0;
        right: 0;
        z-index: 999999;
        pointer-events: none;
    }

    /* BUBBLE */
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
        background: #0084FF;
        color: white;
        border: none;
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
        display: flex;
        flex-direction: column;
        box-shadow: 0 8px 24px rgba(0,0,0,0.25);
    }

    .chat-scroll {
        flex-grow: 1;
        overflow-y: auto;
        padding-right: 10px;
