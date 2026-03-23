import streamlit as st
import uuid
import openai
from field_help import load_field_help


# =========================================================
# 1) Tudásbázis kereső
# =========================================================
def get_kb_answer(question: str, ui_lang: str):
    """
    Egyszerű kulcsszavas keresés a tudásbázisban.
    Ha a kérdés tartalmazza a mező kulcsát → visszaadja a help szöveget.
    """
    kb = load_field_help(ui_lang)
    q = question.lower()

    for key, info in kb.items():
        if key.lower() in q:
            label = info.get("label", "")
            help_text = info.get("help", "")
            return f"**{label}**\n\n{help_text}"

    return None


# =========================================================
# 2) AI válaszgeneráló (OpenAI API)
# =========================================================
def ask_ai(question, ui_lang):
    """
    AI fallback, ha a tudásbázis nem talál releváns mezőt.
    GPT‑4o-mini gyors, olcsó, jó minőség.
    """

    client = openai.OpenAI(api_key=st.secrets["openai"]["api_key"])

    system_prompt_hu = (
        "Segítőkész magyar ügyintéző asszisztens vagy. "
        "Röviden, érthetően, barátságosan válaszolsz. "
        "Az űrlapmezők kitöltésével kapcsolatos kérdésekre segítesz."
    )

    system_prompt_ru = (
        "Вы — дружелюбный помощник, который помогает правильно заполнить форму. "
        "Отвечайте коротко, понятно и доброжелательно, на русском языке."
    )

    system_prompt = system_prompt_hu if ui_lang == "hu" else system_prompt_ru

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question}
        ],
        max_tokens=500
    )

    return response.choices[0].message.content


# =========================================================
# 3) Központi döntési logika: Tudásbázis → AI
# =========================================================
def generate_response(question, ui_lang):
    # 1) Tudásbázis
    kb_answer = get_kb_answer(question, ui_lang)
    if kb_answer:
        return kb_answer

    # 2) AI fallback
    return ask_ai(question, ui_lang)


# =========================================================
# 4) Chat UI
# =========================================================
def render_chat_ai():
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # UI nyelv lekérése (kötelező!)
    ui_lang = st.session_state.get("ui_lang", "hu")

    st.markdown("### 💬 Kérdezzen bátran")

    # Előzmények kiírása
    for role, msg in st.session_state.chat_history:
        st.chat_message(role).write(msg)

    # Új kérdés
    question = st.chat_input("Írja ide kérdését… / Введите свой вопрос…")
    if question:
        st.session_state.chat_history.append(("user", question))

        # Válasz generálása
        answer = generate_response(question, ui_lang)

        st.session_state.chat_history.append(("assistant", answer))
        st.chat_message("assistant").write(answer)


# =========================================================
# 5) Lebegő chat panel
# =========================================================
def floating_chat():
    unique = str(uuid.uuid4()).replace("-", "")

    # Gomb + panel CSS / HTML
    st.markdown(
        f"""
        <style>
        .chat-button-{unique} {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #4a7bd8;
            color: white;
            width: 60px;
            height: 60px;
            border-radius: 50%;
            text-align: center;
            font-size: 28px;
            line-height: 60px;
            cursor: pointer;
            z-index: 99998;
            box-shadow: 0 4px 8px rgba(0,0,0,0.3);
        }}
        #chat-toggle-{unique} {{
            display: none;
        }}
        .chat-panel-{unique} {{
            position: fixed;
            bottom: 100px;
            right: 20px;
            width: 90%;
            max-width: 380px;
            height: 70%;
            background: white;
            border-radius: 12px;
            padding: 12px;
            box-shadow: 0 6px 16px rgba(0,0,0,0.25);
            z-index: 99999;
            display: none;
            overflow-y: auto;
        }}
        #chat-toggle-{unique}:checked ~ .chat-panel-{unique} {{
            display: block;
        }}
        .close-btn-{unique} {{
            position: absolute;
            right: 12px;
            top: 6px;
            font-size: 26px;
            cursor: pointer;
            color: #555;
        }}
        </style>

        <label for="chat-toggle-{unique}" class="chat-button-{unique}">
            💬
        </label>

        <input type="checkbox" id="chat-toggle-{unique}" />

        <div class="chat-panel-{unique}">
            <label for="chat-toggle-{unique}" class="close-btn-{unique}">✖</label>
            <div id="chat-frame-{unique}"></div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Chat render a panelben
    chat_placeholder = st.empty()
    with chat_placeholder.container():
        render_chat_ai()
