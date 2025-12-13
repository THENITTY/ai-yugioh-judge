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
    1. Identifica ogni possibile nome di carta (anche nickname, slang o parziale).
    2. Se possibile, convertilo nel NOME UFFICIALE INGLESE.
    3. Se NON sei sicuro o non trovi il nome ufficiale, restituisci il termine esatto usato dall'utente (es: "Snatchy").
    4. Restituisci una lista JSON di stringhe.

    ESEMPI:
    Input: "Ash nega Desires?"
    Output: ["Ash Blossom & Joyous Spring", "Pot of Desires"]

    Input: "active snatchy on my opponent"
    Output: ["Snatchy"]

    Domanda Utente: "{user_question}"
    
    Output JSON (solo la lista):
    """
    response_text = get_gemini_response(model, prompt)
    
    try:
        start = response_text.find('[')
        end = response_text.rfind(']') + 1
        if start != -1 and end != -1:
            json_str = response_text[start:end]
            return json.loads(json_str)
        return []
    except Exception:
        return []

def get_card_data(card_name):
    # Rimuovi spazi extra per sicurezza
    card_name = card_name.strip()
    url = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
    params = {"fname": card_name}
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            # Prende la corrispondenza migliore (spesso la prima è esatta o fuzzy match)
            return response.json()["data"][0]
        else:
            return None
    except Exception:
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
def load_keys():
    """Carica le chiavi dal file JSON locale."""
    try:
        if os.path.exists("keys.json"):
            with open("keys.json", "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

stored_keys = load_keys()

st.sidebar.title("Configurazione ⚙️")

# Logica Multi-Profilo
if stored_keys:
    # Aggiungi un'opzione vuota/manuale
    options = ["Seleziona un Profilo..."] + list(stored_keys.keys()) + ["🔑 Inserimento Manuale"]
    
    # Se abbiamo già una key in sessione, cerchiamo di capire a quale profilo appartiene (estetica)
    index = 0
    if "active_profile" in st.session_state:
        if st.session_state.active_profile in options:
            index = options.index(st.session_state.active_profile)

    selected_profile = st.sidebar.selectbox("Gestore Chiavi:", options, index=index, key="profile_selector")
    
    if selected_profile in stored_keys:
        st.session_state.api_key = stored_keys[selected_profile]
        st.session_state.active_profile = selected_profile
    elif selected_profile == "🔑 Inserimento Manuale":
        # Reset della key se si passa a manuale e non ce n'è una manuale salvata
        if st.session_state.get("active_profile") != "🔑 Inserimento Manuale":
             st.session_state.api_key = os.getenv("GEMINI_API_KEY", "")
             st.session_state.active_profile = "🔑 Inserimento Manuale"
    else:
        # Caso "Seleziona un Profilo..."
        st.session_state.api_key = ""
        st.session_state.active_profile = ""

# Se non ci sono chiavi salvate o siamo in "Manuale", usiamo la logica standard
if not stored_keys or (st.session_state.get("active_profile") == "🔑 Inserimento Manuale") or (not st.session_state.api_key and "active_profile" not in st.session_state):
    
    # Fallback su variabile d'ambiente standard se non settata
    if "api_key" not in st.session_state:
        st.session_state.api_key = os.getenv("GEMINI_API_KEY", "")

    if not st.session_state.api_key:
        st.sidebar.warning("Nessun profilo selezionato.")
        input_key = st.sidebar.text_input("Inserisci Gemini API Key", type="password")
        if input_key:
            st.session_state.api_key = input_key
            # Salvataggio facoltativo in .env solo se manuale
            with open(".env", "w") as f:
                f.write(f"GEMINI_API_KEY={input_key}")
            st.rerun()
    else:
        # Caso in cui la chiave c'è (da .env o inserita) ma siamo in modalità manuale
        st.sidebar.success("Key Manuale Caricata! ✅")
        if st.sidebar.button("Cambia Key Manuale"):
            st.session_state.api_key = ""
            if os.path.exists(".env"): os.remove(".env") # Opzionale: pulizia
            st.rerun()

elif st.session_state.api_key:
     st.sidebar.success(f"Profilo Attivo: **{selected_profile}** ✅")

if not st.session_state.api_key:
    st.info("👈 Seleziona un Profilo o inserisci una Key per iniziare.")
    st.stop()

# --- Configurazione Gemini ---
try:
    genai.configure(api_key=st.session_state.api_key)
    model, active_model_name = resolve_working_model()
    st.sidebar.caption(f"🤖 Modello: `{active_model_name}`")
except Exception as e:
    st.error(f"Errore critico di configurazione: {e}")
    st.stop()

@st.cache_data
def load_all_card_names():
    """Scarica e cach'a la lista di tutti i nomi delle carte (leggero)."""
    try:
        url = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
        # Scarichiamo tutto il JSON una volta sola (circa 10-15MB, gestibile da Streamlit cloud)
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()["data"]
            return [card["name"] for card in data]
        return []
    except Exception:
        return []

# Caricamento database carte (avviene una volta sola all'avvio)
all_card_names = load_all_card_names()

# --- Configurazione Gemini ---
# (omitted)

# --- UI Principale ---
st.title("AI Yu-Gi-Oh! Judge ⚡️")
st.markdown("### Il tuo assistente per i ruling complessi")

# --- State Management ---
if "step" not in st.session_state:
    st.session_state.step = 1  # 1: Input, 2: Verifica, 3: Verdetto
if "detected_cards" not in st.session_state:
    st.session_state.detected_cards = []
if "question_text" not in st.session_state:
    st.session_state.question_text = ""
if "manual_added_cards" not in st.session_state:
    st.session_state.manual_added_cards = []

# Funzione per reset
def reset_app():
    keys_to_keep = ['api_key', 'active_profile']
    for key in list(st.session_state.keys()):
        if key in keys_to_keep: continue
        del st.session_state[key]
    
    # Re-inizializziamo lo stato base per sicurezza
    st.session_state.step = 1
    st.session_state.detected_cards = []
    st.session_state.manual_added_cards = []
    st.session_state.question_text = ""
    
    st.rerun()

# --- STEP 1: Input Domanda ---
if st.session_state.step == 1:
    with st.expander("ℹ️ Come funziona?"):
        st.write("""
        1. Scrivi lo scenario OPPURE cerca direttamente le carte.
        2. L'IA cercherà di capire le carte dal testo.
        3. Tu potrai confermare o correggere tutto prima del verdetto.
        """)
        
    # Ricerca Universale (Autocomplete)
    st.subheader("1. Cerca Carte (Opzionale)")
    st.caption("Usa questo box per trovare i nomi ufficiali sicuri al 100%:")
    manual_selection = st.multiselect(
        "Aggiungi carte alla busta:", 
        options=all_card_names,
        placeholder="Scrivi 'Ash Blossom', 'Nibiru'...",
        key="search_multiselect"
    )

    st.subheader("2. Descrivi Scenario")
    question_input = st.text_area(
        "Descrivi cosa sta succedendo (usa anche nickname):", 
        placeholder="Esempio: Se attivo 'Snatchy' su...", 
        height=150
    )
    
    if st.button("Analizza Scenario 🔍", type="primary"):
        if not manual_selection:
            st.warning("Per favore seleziona almeno una carta dalla lista.")
        else:
            st.session_state.question_text = question_input
            st.session_state.manual_added_cards = manual_selection
            
            # Modalità strettamente manuale: usiamo solo le carte selezionate
            st.session_state.detected_cards = list(set(manual_selection))
            st.session_state.step = 2
            st.rerun()

# --- STEP 2: Verifica Carte ---
elif st.session_state.step == 2:
    st.info("✅ Carte confermate. Procedi al verdetto.")
    if st.session_state.question_text:
        st.write(f"**Scenario:** *{st.session_state.question_text}*")
    
    st.divider()
    st.subheader("🛠 Busta Carte")
    
    # (Resto del codice di UI carte...) 
    # Manteniamo la logica di visualizzazione ma senza "correzioni AI"
    final_cards_list = []
    
    for i, card in enumerate(st.session_state.detected_cards):
        col_img, col_input = st.columns([0.2, 0.8])
        preview_data = get_card_data(card)
        with col_img:
            if preview_data and "card_images" in preview_data:
                st.image(preview_data["card_images"][0]["image_url_small"], width=80)
            else:
                st.write("🖼️ N/A")
        with col_input:
           new_name = st.text_input(f"Carta #{i+1}", value=card, key=f"card_{i}", label_visibility="collapsed")
           if new_name.strip():
               final_cards_list.append(new_name)

    col_add1, col_add2 = st.columns([0.85, 0.15])
    with col_add1:
        extra_add = st.multiselect("Aggiungi altre carte:", options=all_card_names, key="step2_multiselect")
    
    st.divider()
    
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("🔙 Modifica Domanda"):
            st.session_state.step = 1
            st.rerun()
            
    with col_b2:
        if st.button("Conferma e Giudica 👨‍⚖️", type="primary"):
            full_list = final_cards_list + extra_add
            clean_list = list(set([c.strip() for c in full_list if c.strip()]))
            st.session_state.detected_cards = clean_list
            st.session_state.step = 3
            st.rerun()

# --- STEP 3: Verdetto ---
elif st.session_state.step == 3:
    # (Resto del codice...)
    # Aggiornamento Prompt PIGNOLO
    
    st.subheader("⚖️ Verdetto del Giudice")
    
    found_cards_data = []
    cards_context = ""
    missing_cards = []

    with st.status("Consultazione Database Ufficiale...", expanded=True):
        progress_bar = st.progress(0)
        total_cards = len(st.session_state.detected_cards)
        
        for idx, card_name in enumerate(st.session_state.detected_cards):
            st.write(f"🔍 Cerco: **{card_name}**...")
            card_data = get_card_data(card_name)
            if card_data:
                found_cards_data.append(card_data)
                cards_context += f"NOME UFFICIALE: {card_data['name']}\nTESTO AGGIORNATO: {card_data['desc']}\n\n"
                st.success(f"✅ Trovata: {card_data['name']}")
            else:
                missing_cards.append(card_name)
                st.error(f"❌ Non trovata: {card_name}")
            if total_cards > 0: progress_bar.progress((idx + 1) / total_cards)
    
    with st.spinner("Generazione verdetto in corso..."):
        prompt_ruling = f"""
        Sei un **HEAD JUDGE UFFICIALE DI YU-GI-OH** (Livello 3).
        Il tuo compito è emettere ruling tecnici estremamente precisi e pignoli.

        REGOLAMENTO CRITICO:
        - **Damage Step**: Sii ESTREMAMENTE severo. Solo carte che modificano direttamente ATK/DEF, Counter Traps, o effetti che negano specificamente *l'attivazione* (non l'effetto) possono essere attivate qui (salvo eccezioni esplicite).
        - **Esempio Pignolo**: "Ash Blossom & Joyous Spring" NEGA L'EFFETTO, NON l'attivazione. Quindi NON PUÒ quasi mai essere usata nel Damage Step. Se l'utente chiede questo, devi dire di NO e spiegare brutalmente perché.
        - **Conjunctions**: Fai attenzione a "E", "ANCHE SE", "POI".
        - **Spell Speed**: Rispetta rigorosamente le velocità di attivazione.

        TESTI UFFICIALI (Fonte di Verità):
        ---
        {cards_context}
        ---

        SCENARIO UTENTE:
        "{st.session_state.question_text}"

        ISTRUZIONI:
        1. Analizza lo scenario cercando cavilli legali.
        2. Se la mossa è illegale, dillo chiaramente.
        3. Usa terminologia ufficiale (Activation, Resolution, SEGOC, Turn Player Priority).
        
        FORMATO RISPOSTA RICHIESTO:
        Devi dividere la risposta in due parti separate da una riga con scritto esattamente "---DETTAGLI---".
        
        Parte 1 (Prima di ---DETTAGLI---):
        - Risposta diretta e concisa (es: "Sì, [Carta X] nega [Carta Y]" oppure "No, mossa illegale").
        
        ---DETTAGLI---
        
        Parte 2 (Dopo ---DETTAGLI---):
        - Analisi tecnica step-by-step.
        - Cita le regole del Damage Step se rilevante.
        """
        
        response = get_gemini_response(model, prompt_ruling)
        
        # Parsing della risposta splittata
        if "---DETTAGLI---" in response:
            short_answer, deep_dive = response.split("---DETTAGLI---")
        else:
            short_answer = response
            deep_dive = "Nessun dettaglio tecnico aggiuntivo fornito."

        st.success("Verdetto Rapido:")
        st.markdown(short_answer)
        
        with st.expander("🧐 Spiegazione Tecnica Approfondita"):
            st.markdown(deep_dive.strip())
        
    if st.button("Nuova Domanda 🔄"):
        reset_app()
