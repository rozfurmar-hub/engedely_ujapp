import streamlit as st

import uuid

from field_help import load_field_help

def get_kb_answer(question: str, ui_lang: str):
    """
    Egyszerű kulcsszavas keresés a tudásbázisban.
    Ha a kérdés tartalmazza a mező kulcsát → visszaadja a help szöveget.
    """
    kb = load_field_help(ui_lang)
    q = question.lower()

    for key, info in kb.items():
        if key.lower() in q:
            # Elsődleges: a help szöveg
            help_text = info.get("help", "")

            # Ha a label releváns, az is visszaadható:
            label = info.get("label", "")

            return f"**{label}**\n\n{help_text}"

    return None

# ---- CHAT LOGIKA ----
def generate_response(question, ui_lang):
    # 1) Tudásbázis (mezőmagyarázat)
    kb_answer = get_kb_answer(question, ui_lang)
    if kb_answer:
        return kb_answer

    # 2) AI fallback
    import openai

    def ask_ai(question, ui_lang):
        # OpenAI kliens inicializálása
        client = openai.OpenAI(api_key=st.secrets["openai"]["api_key"])
    
        system_prompt_hu = """Segítőkész magyar ügyintéző asszisztens vagy. 
    Röviden, érthetően, barátságosan válaszolsz. Az űrlapmezők kitöltésével kapcsolatos kérdésekre segítesz."""
    
        system_prompt_ru = """Вы — дружелюбный помощник, объясняющий, как заполнять форму.
    Отвечайте коротко, понятно и дружелюбно, на русском языке."""
    
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

def render_chat_ai():
        if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
        
        ui_lang = st.session_state.get
    
    st.markdown("### 💬 Kérdezzen bátran")

    for role, msg in st.session_state.chat_history:
        st.chat_message(role).write(msg)

    question = st.chat_input("Írja ide kérdését… / Введите свой вопрос…")
    if question:
        st.session_state.chat_history.append(("user", question))
        answer = generate_response(question, ui_lang)
        st.session_state.chat_history.append(("assistant", answer))
        st.chat_message("assistant").write(answer)

# ---- FŐ FUNKCIÓ: LEBEGŐ CHAT ----
def floating_chat():
    unique = str(uuid.uuid4()).replace("-", "")

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

    # A chat tartalma kizárólag a panelben jelenjen meg
    chat_placeholder = st.empty()

    with chat_placeholder.container():
        render_chat_ai()
