import streamlit as st
import uuid

# ---- CHAT LOGIKA ----
def generate_ai_answer(q):
    # Egyelőre minta — ide kerül majd az AI
    return f"AI válasz (minta): {q}"

def render_chat_ai():
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    st.markdown("### 💬 Kérdezzen bátran")

    for role, msg in st.session_state.chat_history:
        st.chat_message(role).write(msg)

    question = st.chat_input("Írja ide kérdését… / Введите свой вопрос…")

    if question:
        st.session_state.chat_history.append(("user", question))
        answer = generate_ai_answer(question)
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
