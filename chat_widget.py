import streamlit as st
import openai
from field_help import load_field_help

# =========================================================
# Tudásbázis kereső
# =========================================================
def get_kb_answer(question: str, ui_lang: str):
    kb = load_field_help(ui_lang)
    q = question.lower()
    for key, info in kb.items():
        if key.lower() in q:
            return f"**{info.get('label','')}**\n\n{info.get('help','')}"
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
# AI fallback
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
        "Отвечайте коротко и понятно."
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
# Tudásbázis → AI válasz
# =========================================================
def generate_response(question, ui_lang):
    kb_answer = get_kb_answer(question, ui_lang)
    if kb_answer:
        return kb_answer
    return ask_ai(question, ui_lang)

# =========================================================
# Messenger-szerű lebegő chat — stabil verzió
# =========================================================
def floating_chat():

    # STATE
    if "chat_open" not in st.session_state:
        st.session_state.chat_open = False
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # CSS + HTML overlay
    st.markdown("""
<style>

#chat-root {
    position: fixed;
    bottom: 0;
    right: 0;
    z-index: 999999;
    pointer-events: none;
}

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
}

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

/* hidden toggle button */
button[data-testid="chat_toggle_btn"] {
    display: none !important;    
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


""", unsafe_allow_html=True)

    # STREAMLIT TOGGLE BUTTON (hidden but JS-clickable)
    toggled = st.button("???  CHAT  ???", key="chat_toggle_btn")
    if toggled:
        st.session_state.chat_open = not st.session_state.chat_open

    # If closed → exit
    if not st.session_state.chat_open:
        return

    # CHAT PANEL
       
    panel = st.container()
    with panel:
        st.markdown('<div class="chat-panel">', unsafe_allow_html=True)
    
        # Scroll area
        st.markdown('<div class="chat-scroll">', unsafe_allow_html=True)
    
        # Placeholder (ha nincsenek üzenetek)
        if not st.session_state.chat_messages:
            st.markdown(
                '<div class="bubble-ai" style="opacity:0.6;">Kérdése van? / Есть вопросы?</div>',
                unsafe_allow_html=True
            )
        else:
            for role, txt in st.session_state.chat_messages:
                css = "bubble-user" if role == "user" else "bubble-ai"
                st.markdown(f'<div class="{css}">{txt}</div>', unsafe_allow_html=True)
    
        st.markdown("</div>", unsafe_allow_html=True)


        # Ha korábbi üzenet törlésre vár (az előző ciklusból)
        if "chat_input_text" in st.session_state and st.session_state.chat_input_text:
            # Ha épp most fejeztünk be egy üzenetet, töröljük mielőtt megjelenne az input
            if st.session_state.get("clear_chat_input", False):
                st.session_state.pop("chat_input_text", None)
                st.session_state["clear_chat_input"] = False

        
        # Chat Input mező

        user_msg = st.text_input(
            "",
            key="chat_input_text",
            placeholder="Tegye fel kérdését! / Задайте вопрос!"
        )
    
        if user_msg:
            st.session_state.chat_messages.append(("user", user_msg))
            ai = generate_response(user_msg, st.session_state.get("ui_lang", "hu"))
            st.session_state.chat_messages.append(("assistant", ai))

            # Jelöljük, hogy a következő renderciklus előtt üríteni kell az inputot
            st.session_state["clear_chat_input"] = True

            st.rerun()
