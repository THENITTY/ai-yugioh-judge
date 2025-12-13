import os
import streamlit as st
import google.generativeai as genai
import requests
import json
import time
from dotenv import load_dotenv

# Carica variabili d'ambiente da .env se presente
load_dotenv()

# --- Configurazione Pagina ---
st.set_page_config(
    page_title="AI Yu-Gi-Oh! Judge",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Stile Personalizzato ---
st.markdown("""
<style>
    .stTextArea textarea { font-size: 16px; }
</style>
""", unsafe_allow_html=True)

# --- Funzioni di Supporto ---

def get_gemini_response(model, prompt):
    """Genera una risposta usando il modello Gemini con retry automatico per Rate Limit (429)."""
    max_retries = 3
    base_delay = 5  # secondi
    
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower():
                if attempt < max_retries - 1:
                    wait_time = base_delay * (attempt + 1)
                    st.toast(f"⚠️ Rate limit raggiunto. Riprovo tra {wait_time}s... ({attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
            return f"Errore API Gemini: {e}"
    return "Errore: Rate limit persistente. Riprova più tardi."

def extract_cards(model, user_question):
    prompt = f"""
    Sei un esperto di Yu-Gi-Oh!. Identifica le carte menzionate nella domanda.
    
    COMPITO:
    1. Identifica ogni possibile nome di carta (anche parziale o slang).
    2. Convertilo nel NOME UFFICIALE INGLESE (es: "Ash" -> "Ash Blossom & Joyous Spring").
    3. Restituisci una lista JSON di stringhe.

    ESEMPI:
    Input: "Ash nega Desires?"
    Output: ["Ash Blossom & Joyous Spring", "Pot of Desires"]

    Input: "Posso attivare eff veiler su kash unicorn?"
    Output: ["Effect Veiler", "Kashtira Unicorn"]

    Domanda Utente: "{user_question}"
    
    Output JSON (solo la lista):
    """
    response_text = get_gemini_response(model, prompt)
    
    # Debug visibile (per capire cosa succede)
    with st.expander("🛠 Debug Estrazione (Raw)"):
        st.code(response_text)

    # Pulizia JSON più robusta
    try:
        start = response_text.find('[')
        end = response_text.rfind(']') + 1
        if start != -1 and end != -1:
            json_str = response_text[start:end]
            return json.loads(json_str)
        return []
    except Exception:
        return []
    except json.JSONDecodeError:
        return []

def get_card_data(card_name):
    url = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
    params = {"fname": card_name}
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            return response.json()["data"][0]
        else:
            print(f"API Error for {card_name}: {response.status_code}")
            return None
    except Exception as e:
        print(f"Exception for {card_name}: {e}")
        return None

def resolve_working_model():
    """Tenta automaticamente di trovare un modello funzionante."""
    candidate_models = [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "gemini-flash-latest",
        "gemini-pro-latest",
        "gemini-1.5-flash"
    ]
    
    for model_name in candidate_models:
        try:
            model = genai.GenerativeModel(model_name)
            return model, model_name
        except Exception:
            continue
            
    return genai.GenerativeModel("gemini-2.5-flash"), "gemini-2.5-flash (Default)"

# --- Gestione Autenticazione ---
if "api_key" not in st.session_state:
    st.session_state.api_key = os.getenv("GEMINI_API_KEY", "")

st.sidebar.title("Configurazione ⚙️")

# Se la chiave non è in sessione o env, chiedila
if not st.session_state.api_key:
    input_key = st.sidebar.text_input("Inserisci Gemini API Key", type="password")
    if input_key:
        st.session_state.api_key = input_key
        # Salva nel file .env per il futuro
        with open(".env", "w") as f:
            f.write(f"GEMINI_API_KEY={input_key}")
        st.rerun()
else:
    st.sidebar.success("API Key caricata! ✅")
    if st.sidebar.button("Cambia Key"):
        st.session_state.api_key = ""
        if os.path.exists(".env"):
            os.remove(".env")
        st.rerun()

if not st.session_state.api_key:
    st.warning("Inserisci la API Key nella sidebar per iniziare.")
    st.stop()

# --- Configurazione Gemini ---
try:
    genai.configure(api_key=st.session_state.api_key)
    
    # Smart Resolve del Modello
    model, active_model_name = resolve_working_model()
    st.sidebar.caption(f"🤖 Modello: `{active_model_name}`")

except Exception as e:
    st.error(f"Errore critico di configurazione: {e}")
    st.stop()

# --- UI Principale ---
st.title("AI Yu-Gi-Oh! Judge ⚖️")
st.markdown("### Il tuo assistente per i ruling complessi")

with st.expander("ℹ️ Come funziona?"):
    st.write("""
    1. Scrivi la tua domanda o scenario di gioco.
    2. L'IA identificherà le carte coinvolte.
    3. Scaricherà i testi aggiornati dal Database Ufficiale.
    4. Ti fornirà un ruling basato ESATTAMENTE su quei testi.
    """)

question = st.text_area("Descrivi lo scenario:", placeholder="Esempio: Se il mio avversario attiva 'Ash Blossom'...")

if st.button("Chiedi al Giudice 👨‍⚖️"):
    if not question:
        st.warning("Scrivi una domanda prima.")
    else:
        with st.spinner("Consultando il regolamento..."):
            with st.status("Analisi in corso...", expanded=True) as status:
                st.write("🔍 Identificazione carte...")
                extracted_cards = extract_cards(model, question)
                
                found_cards_data = []
                cards_context = ""
                
                if extracted_cards:
                    # Debug visibile fuori dallo status per conferma
                    st.info(f"Carte identificate dall'IA: {extracted_cards}")
                    
                    st.write(f"📝 Carte rilevate: {', '.join(extracted_cards)}")
                    progress_bar = st.progress(0)
                    
                    for idx, card_name in enumerate(extracted_cards):
                        card_data = get_card_data(card_name)
                        if card_data:
                            found_cards_data.append(card_data)
                            cards_context += f"NOME: {card_data['name']}\nTESTO: {card_data['desc']}\n\n"
                        else:
                            st.error(f"❌ Impossibile trovare dati per: '{card_name}' nel database YGOPro.")
                        
                        progress_bar.progress((idx + 1) / len(extracted_cards))
                    
                    status.update(label="Analisi completata!", state="complete", expanded=False)
                else:
                    status.update(label="Nessuna carta rilevata", state="complete")

            if found_cards_data:
                with st.expander(f"Carte trovate ({len(found_cards_data)})"):
                    for c in found_cards_data:
                        st.text(f"{c['name']}:\n{c['desc']}")
                        st.divider()

            prompt_ruling = f"""
            Sei un Giudice Ufficiale di Yu-Gi-Oh. Il tuo compito è emettere un ruling corretto basato sul regolamento ufficiale (Konami).

            DATI CARTE (Questi sono i testi ufficiali aggiornati, usali come Fonte di Verità per gli effetti):
            ---
            {cards_context}
            ---

            DOMANDA UTENTE:
            "{question}"

            ISTRUZIONI:
            1. Analizza gli effetti delle carte forniti qui sopra.
            2. Applica le Regole Generali del gioco (es. Damage Step, Spell Speeds, catene, priorità) che conosci come esperto.
            3. Combina le due cose per rispondere alla domanda.
            4. Se una carta non può essere attivata in una certa fase (es. Damage Step) per regole di gioco, spiegalo chiaramente citando la meccanica.

            RISPOSTA (Sii conciso e professionale):
            """
            
            # Debug Prompt
            with st.expander("🛠 Debug Ruling Prompt"):
                st.code(prompt_ruling)

            ruling_response = get_gemini_response(model, prompt_ruling)
            
            # Debug Response
            with st.expander("🛠 Debug Ruling Response (Raw)"):
                st.write(ruling_response)
            
            st.success("Verdetto:")
            st.markdown(ruling_response)
