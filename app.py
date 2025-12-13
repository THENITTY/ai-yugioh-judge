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
if "api_key" not in st.session_state:
    st.session_state.api_key = os.getenv("GEMINI_API_KEY", "")

st.sidebar.title("Configurazione ⚙️")

if not st.session_state.api_key:
    input_key = st.sidebar.text_input("Inserisci Gemini API Key", type="password")
    if input_key:
        st.session_state.api_key = input_key
        with open(".env", "w") as f:
            f.write(f"GEMINI_API_KEY={input_key}")
        st.rerun()
else:
    st.sidebar.success("API Key caricata! ✅")
    if st.sidebar.button("Cambia Key"):
        st.session_state.api_key = ""
        st.rerun()

if not st.session_state.api_key:
    st.warning("Inserisci la API Key nella sidebar per iniziare.")
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
    for key in list(st.session_state.keys()):
        if key == 'api_key': continue # Manteniamo la API Key
        del st.session_state[key]
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
    
    # Opzione per disabilitare l'IA
    use_ai = st.checkbox("🕵️ Attiva riconoscimento automatico carte dal testo", value=True, help="Se disattivato, verranno usate SOLO le carte selezionate manualmente sopra.")

    if st.button("Analizza Scenario 🔍", type="primary"):
        if not question_input and not manual_selection:
            st.warning("Scrivi una domanda o seleziona almeno una carta.")
        else:
            st.session_state.question_text = question_input
            st.session_state.manual_added_cards = manual_selection
            
            with st.spinner("Analisi in corso..."):
                if question_input and use_ai:
                    extracted = extract_cards(model, question_input)
                else:
                    extracted = []
                
                # Uniamo le carte trovate dall'IA con quelle selezionate a mano (evitando duplicati)
                combined_cards = list(set(extracted + manual_selection))
                
                st.session_state.detected_cards = combined_cards
                st.session_state.step = 2
                st.rerun()

# --- STEP 2: Verifica Carte ---
elif st.session_state.step == 2:
    st.info("✅ Analisi completata. Conferma la lista delle carte.")
    if st.session_state.question_text:
        st.write(f"**Scenario:** *{st.session_state.question_text}*")
    
    st.divider()
    st.subheader("🛠 Busta Carte")
    st.caption("Ecco le carte che verranno analizzate. Modifica i nomi se l'IA ha sbagliato.")

    # Gestione dinamica lista carte
    final_cards_list = []
    
    # Mostra input per ogni carta trovata
    for i, card in enumerate(st.session_state.detected_cards):
        # Layout a colonne: Immagine - Input
        col_img, col_input = st.columns([0.2, 0.8])
        
        # Recuperiamo info al volo per l'immagine
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

    # Bottone per aggiungere carta manuale (extra fallback)
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
            # Aggiungi le carte extra selezionate nello step 2
            full_list = final_cards_list + extra_add
            # Rimuovi duplicati e stringhe vuote
            clean_list = list(set([c.strip() for c in full_list if c.strip()]))
            
            st.session_state.detected_cards = clean_list
            st.session_state.step = 3
            st.rerun()

# --- STEP 3: Verdetto ---
elif st.session_state.step == 3:
    st.subheader("⚖️ Verdetto del Giudice")
    
    found_cards_data = []
    cards_context = ""
    missing_cards = []

    with st.status("Consultazione Database Ufficiale...", expanded=True):
        progress_bar = st.progress(0)
        total_cards = len(st.session_state.detected_cards)
        
        if total_cards == 0:
            st.warning("Nessuna carta selezionata. Procedo con le regole generali.")
            
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
            
            if total_cards > 0:
                progress_bar.progress((idx + 1) / total_cards)
    
    # Se ci sono carte non trovate, avvisa ma procedi
    if missing_cards:
        st.warning(f"Attenzione: Non ho trovato i testi ufficiali per: {', '.join(missing_cards)}. Il verdetto potrebbe essere meno preciso.")

    # Generazione Verdetto
    with st.spinner("Generazione verdetto in corso..."):
        prompt_ruling = f"""
        Sei un Giudice Ufficiale di Yu-Gi-Oh. Emetti un ruling basato sul regolamento.

        TESTI UFFICIALI (Fonte di Verità):
        ---
        {cards_context}
        ---

        SCENARIO UTENTE:
        "{st.session_state.question_text}"

        ISTRUZIONI:
        1. Analizza lo scenario e i testi.
        2. Applica le Regole Ufficiali (Damage Step, Chain, Targeting, etc.).
        3. Spiega il verdetto.
        
        FORMATO RISPOSTA RICHIESTO:
        Devi dividere la risposta in due parti separate da una riga con scritto esattamente "---DETTAGLI---".
        
        Parte 1 (Prima di ---DETTAGLI---):
        - Risposta diretta e concisa (es: "Sì, [Carta X] nega [Carta Y]").
        - Una breve spiegazione di 2-3 frasi massimo.
        
        ---DETTAGLI---
        
        Parte 2 (Dopo ---DETTAGLI---):
        - Spiegazione tecnica approfondita.
        -cita le catene (Chain Links), Spell Speeds, e meccaniche specifiche.
        - Riferimenti precisi al testo delle carte.
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
