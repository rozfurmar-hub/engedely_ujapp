import streamlit as st
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
        "Отвечайте коротко и понятно, на русском языке."
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

        /* BUBORÉK */
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
