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
    if "show_chat" not in st.session_state:
        st.session_state.show_chat = False

    st.markdown("""
<style>
/* Rejtse el a fő tartalmi chat konténert */
.block-container > div:has(.stChatInputContainer) {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)

    # Lebegő gomb st.button-ként (NEM HTML!)
    chat_button_style = """
    <style>
        .floating-chat-btn {
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 10000;
        }
        .floating-chat-panel {
            position: fixed;
            bottom: 90px;
            right: 20px;
            width: 360px;
            height: 480px;
            background: white;
            border-radius: 12px;
            padding: 10px;
            box-shadow: 0 6px 16px rgba(0,0,0,0.25);
            z-index: 10001;
            overflow-y: auto;
        }
    </style>
    """
    st.markdown(chat_button_style, unsafe_allow_html=True)

    # lebegő gomb container
    chat_button_container = st.container()
    with chat_button_container:
        st.markdown('<div class="floating-chat-btn">', unsafe_allow_html=True)
        if st.button("💬", key="open_chat"):
            st.session_state.show_chat = not st.session_state.show_chat
        st.markdown("</div>", unsafe_allow_html=True)

    # Ha nincs megnyitva → kilépünk
    if not st.session_state.show_chat:
        return

    # A lebegő panel tényleges Streamlit konténere
    panel = st.container()

    with panel:
        st.markdown('<div class="floating-chat-panel">', unsafe_allow_html=True)

        # ITT jelenik meg a chat! → ez most működni fog
        render_chat_ai()

        st.markdown('</div>', unsafe_allow_html=True)
