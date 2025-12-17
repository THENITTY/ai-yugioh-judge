# IMPORTS
import os
import gc # FIX: Added missing import
import streamlit as st
import google.generativeai as genai
import requests
import json
import time
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dotenv import load_dotenv
from duckduckgo_search import DDGS
from yugioh_scraper import YuGiOhMetaScraper
from PIL import Image
import pandas as pd

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

@st.cache_data
def load_card_database():
    """Scarica DB carte (Nome -> Tipo). Light version."""
    try:
        url = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
        # Timeout added to prevent freeze
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()["data"]
            # Map: "Dark Magician" -> "Normal Monster"
            db = {}
            for card in data:
                db[card["name"]] = card["type"]
            return db
        return {}
    except Exception as e:
        print(f"DB Load Error: {e}")
        return {}

@st.cache_data
def load_all_card_names():
    """Scarica e catch'a la lista di tutti i nomi delle carte (leggero)."""
    try:
        url = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()["data"]
            return [card["name"] for card in data]
        return []
    except Exception:
        return []

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

def analyze_image_for_cards(model, image):
    """Analizza un'immagine con Gemini Vision per trovare carte."""
    prompt = """
    Sei un giocatore esperto di Yu-Gi-Oh!.
    
    COMPITO:
    Analizza questa foto del tavolo da gioco. Identifica le carte visibili.
    
    ATTENZIONE - ROTAZIONE:
    - Molte carte sono in "Posizione di Difesa" (ruotate di 90°) o capovolte.
    - RUOTA MENTALMENTE l'immagine per leggere il testo scritto in alto.
    - NON farti ingannare dall'orientamento.
    
    STRATEGIA (OCR + COLORI):
    1. Leggi il nome.
    2. Controlla il colore del bordo:
       - BLU con Esagoni = LINK. (Es: "Backup @Ignister"). Se leggi "Backup Supervisor" ma è BLU, allora è "@Ignister"!
       - NERO = XYZ.
       - VIOLA = FUSIONE.
       - VERDE = MAGIA.
    
    ISTRUZIONI:
    - Restituisci SOLO i nomi ufficiali inglesi.
    - Se leggi "Ripper" e vedi un mostro XYZ, deduci "K9-17 'Ripper'".
    - Fai attenzione alle VIRGOLETTE nel nome (es: "A Case for K9" potrebbe averle).
    - NON INVENTARE NOMI.
    
    Output richiesto:
    Un oggetto JSON con due chiavi:
    1. "cards": Lista di stringhe coi nomi esatti.
    2. "situation": Una descrizione breve (in Italiano) di chi controlla cosa, la posizione (Attacco/Difesa) e la zona, basandoti sulla prospettiva (Chi fotografa è il Giocatore di Turno/Bottom side).
    
    Esempio:
    {
      "cards": ["Super Starslayer TY-PHON - Sky Crisis", "Linguriboh"],
      "situation": "Il giocatore controlla Linguriboh nella zona Main Monster. L'avversario ha TY-PHON in attacco."
    }
    """
    
    try:
        response = model.generate_content([prompt, image])
        response_text = response.text
        
        # Cleanup Markdown
        cleaned_text = response_text.replace("```json", "").replace("```", "").strip()
        
        start = cleaned_text.find('{')
        end = cleaned_text.rfind('}') + 1
        if start != -1 and end != -1:
            json_str = cleaned_text[start:end]
            return json.loads(json_str)
        
        # Return raw text if parsing fails (for debugging)
        return {"error": "parsing_failed", "raw": response_text}
    except Exception as e:
        st.error(f"Errore Vision: {e}")
        return {}
        st.error(f"Errore Vision: {e}")
        return []

def scrape_deck_list(deck_url):
    """Estrae la lista carte da una pagina deck di YGOProDeck."""
    try:
        if not deck_url.startswith("http"):
            deck_url = f"https://ygoprodeck.com{deck_url}"
            
        # Headers standard già definiti globalmente, o usiamone di nuovi
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        response = requests.get(deck_url, headers=headers, timeout=10)
        if response.status_code != 200:
            return "Errore download deck."
            
        soup = BeautifulSoup(response.text, 'html.parser')
        deck_text = []
        
        raw_main = []
        raw_side = []
        raw_extra = []

        # Cerca i container delle carte (Main, Extra, Side)
        # YGOProDeck usa div con id="main_deck", "extra_deck", "side_deck"
        # Le carte sono immagini con class="lazy" (o "master-duel-card") e attr "data-cardname"
        for section_id, section_name in [("main_deck", "Main Deck"), ("extra_deck", "Extra Deck"), ("side_deck", "Side Deck")]:
            section_div = soup.find('div', {'id': section_id})
            if section_div:
                cards = []
                # Trova tutte le immagini delle carte
                # Nota: la classe può variare, ma data-cardname è costante
                for img in section_div.find_all('img'):
                    name = img.get('data-cardname')
                    src = img.get('data-src') or img.get('src') # Fallback
                    if name:
                        cards.append((name, src))
                
                if cards:
                    # Conta le carte (es. 3x Ash Blossom)
                    from collections import Counter
                    # cards è una lista di tuple (name, src). Dobbiamo contare i nomi ma tenere un riferimento alla src.
                    
                    card_names = [c[0] for c in cards] # Solo nomi per il conteggio
                    card_map = {c[0]: c[1] for c in cards} # Mappa Nome -> URL
                    
                    counts = Counter(card_names)
                    
                    # Ordina per numero copie decrescente
                    card_lines = []
                    
                    # Create structured list for analysis
                    structured_list = [] # List of {"amount": N, "card": {"name": "..."}}

                    for name, count in counts.most_common():
                        url = card_map.get(name, "")
                        # Salviamo nel contesto in formato: "3x Name <URL>" così l'LLM lo può parsare
                        card_lines.append(f"{count}x {name} <{url}>")
                        
                        # Populate structured raw data
                        structured_list.append({"amount": count, "card": {"name": name, "image": url}})

                    deck_text.append(f"**{section_name}**:")
                    deck_text.append(", ".join(card_lines))
                    
                    # Save to specific raw lists
                    if section_id == "main_deck":
                        raw_main = structured_list
                    elif section_id == "side_deck":
                        raw_side = structured_list
                    elif section_id == "extra_deck":
                        raw_extra = structured_list
                    
        return ("\n".join(deck_text) if deck_text else "Nessuna carta trovata.", raw_main, raw_side, raw_extra)
    except Exception as e:
        return (f"Errore scraping deck: {e}", [], [], [])

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
    """Carica le chiavi da Streamlit Secrets (Cloud) o file JSON locale."""
    keys = {}
    
    # 1. Priorità: Streamlit Secrets (Cloud)
    try:
        if "stored_keys" in st.secrets:
            # Convertiamo to_dict per sicurezza
            return dict(st.secrets["stored_keys"])
    except FileNotFoundError:
        pass # Nessun secrets.toml trovato in locale, normale
        
    # 2. Fallback: JSON Locale
    try:
        if os.path.exists("keys.json"):
            with open("keys.json", "r") as f:
                return json.load(f)
    except Exception:
        pass
        
    return keys

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
except Exception as e:
    st.error(f"Errore critico di configurazione: {e}")
    st.stop()

# --- Navigazione Modalità ---
st.sidebar.markdown("---")
st.sidebar.subheader("📱 Modalità")
mode = st.sidebar.radio("Seleziona App:", ["👨‍⚖️ AI Judge", "📊 Meta Analyst"], label_visibility="collapsed")

# --- UI Principale ---
if mode == "👨‍⚖️ AI Judge":
    st.title("AI Yu-Gi-Oh! Judge ⚖️")
    st.markdown("### Il tuo assistente per i ruling complessi")

    # Inizializza modello standard per Judge
    model, active_model_name = resolve_working_model()
    st.sidebar.caption(f"🤖 Modello Judge: `{active_model_name}`")




    # Caricamento database carte (avviene una volta sola all'avvio)
    all_card_names = load_all_card_names()

    # --- State Management Judge ---
    if "step" not in st.session_state:
        st.session_state.step = 1  # 1: Input, 2: Verifica, 3: Verdetto
    if "detected_cards" not in st.session_state:
        st.session_state.detected_cards = []
    if "question_text" not in st.session_state:
        st.session_state.question_text = ""
    if "manual_added_cards" not in st.session_state:
        st.session_state.manual_added_cards = []
    
    # Initialize Watchdog for Chat
    if "judge_chat_history" not in st.session_state:
        st.session_state.judge_chat_history = []

    # Funzione per reset Judge
    def reset_judge():
        keys_to_keep = ['api_key', 'active_profile']
        for key in list(st.session_state.keys()):
            if key in keys_to_keep: continue
            del st.session_state[key]
        
        st.session_state.step = 1
        st.session_state.detected_cards = []
        st.session_state.manual_added_cards = []
        st.session_state.question_text = ""
        
        # Reset Chat & Persistence
        st.session_state.judge_chat_history = []
        st.session_state.verdict_ready = False
        st.session_state.verdict_short = ""
        st.session_state.verdict_deep = ""
        
        st.rerun()

    # --- STEP 1: Input Domanda ---
    # --- STEP 1: Input Domanda ---
    if st.session_state.step == 1:
        # (Expander Removed as requested)
            
        # Ricerca Universale (Autocomplete)
        st.subheader("1. Seleziona Carte")
        st.caption("Usa questo box per trovare i nomi ufficiali sicuri al 100%:")
        
        # Persistence Logic: Pre-fill if returning from Step 2
        default_cards = st.session_state.get("detected_cards", [])
        # Filter to ensure they are in options (safety check)
        default_cards = [c for c in default_cards if c in all_card_names]
        
        manual_selection = st.multiselect(
            "Carte Coinvolte:", 
            options=all_card_names,
            default=default_cards,
            placeholder="Scrivi 'Ash Blossom', 'Nibiru'...",
            key="search_multiselect"
        )

        st.subheader("2. Descrivi Scenario")
        question_input = st.text_area(
            "Domanda / Situazione:", 
            value=st.session_state.get("question_text", ""),
            placeholder="Esempio: Se attivo 'Snatchy' su...", 
            height=150
        )
        
        # --- NEW: Image Upload ---
        st.subheader("3. Analisi Foto Campo 📸")
        uploaded_file = st.file_uploader("Carica una foto del terreno di gioco:", type=["jpg", "jpeg", "png"])
        
        st.divider()
        
        # Consolidated Action Button Area
        # Logic: If photo -> Button "Vision", Else -> Button "Text"
        if uploaded_file is not None:
             # Photo Uploaded -> Priority Action is Vision
             if st.button("📸 Analizza Foto + Scenario", type="primary", use_container_width=True):
                    with st.spinner("👀 L'AI sta guardando la foto..."):
                         try:
                             image = Image.open(uploaded_file)
                             
                             # 1. Vision Analysis
                             vision_cards = []
                             vision_model, _name = resolve_working_model()
                             vision_data = analyze_image_for_cards(vision_model, image)
                             
                             vision_cards = []
                             situation_desc = ""

                             
                             # Check for errors/raw text first
                             if isinstance(vision_data, dict):
                                 if "error" in vision_data:
                                     st.warning("⚠️ Errore lettura AI.")
                                     # with st.expander("Raw"): st.write(vision_data["raw"])
                                 else:
                                     vision_cards = vision_data.get("cards", [])
                                     situation_desc = vision_data.get("situation", "")
                             
                             # --- FUZZY MATCHING CORRECTION ---
                             import difflib
                             vision_cards_corrected = []
                             
                             if vision_cards:
                                 for raw_name in vision_cards:
                                     # Try exact match first
                                     if raw_name in all_card_names:
                                         vision_cards_corrected.append(raw_name)
                                     else:
                                         # Try Fuzzy Match
                                         matches = difflib.get_close_matches(raw_name, all_card_names, n=1, cutoff=0.5)
                                         if matches:
                                             st.toast(f"Corretto: {raw_name} -> {matches[0]}")
                                             vision_cards_corrected.append(matches[0])
                                         else:
                                             vision_cards_corrected.append(raw_name)
                                 vision_cards = vision_cards_corrected
                                 st.toast(f"Trovate {len(vision_cards)} carte!")
                             else:
                                 st.warning("Nessuna carta identificata con certezza.")
                                 
                             # 2. Merge everything
                             total_cards = list(set(manual_selection + vision_cards))
                             
                             # Pre-fill specific situation if found
                             final_question = question_input
                             if situation_desc:
                                 st.info(f"📝 Situazione rilevata: {situation_desc}")
                                 # Append to description if not already there
                                 final_question = f"{question_input}\n\n[CONTESTO VISIVO RILEVATO DALL'AI]: {situation_desc}"
                             
                             st.session_state.question_text = final_question
                             st.session_state.detected_cards = total_cards
                             st.session_state.step = 2
                             st.rerun()
                             
                         except Exception as e:
                             st.error(f"Errore caricamento immagine: {e}")
                             
        else:
             # Text Only Mode
             if st.button("Analizza Scenario (Testo) 🔍", type="primary", use_container_width=True):
                if not manual_selection and not question_input:
                     st.warning("Scrivi qualcosa o seleziona una carta.")
                else:
                     st.session_state.question_text = question_input
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
        
        # --- CALLBACK LOGIC START ---
        def add_cards_callback():
            """Adds selected cards to the main list and clears the widget."""
            new_selection = st.session_state.step2_multiselect
            current_cards = st.session_state.detected_cards
            
            # Add unique new cards
            for card in new_selection:
                if card not in current_cards:
                    current_cards.append(card)
                    # Optional: Toast feedback
                    # st.toast(f"Aggiunto: {card}")
            
            # Update main list
            st.session_state.detected_cards = current_cards
            # Clear the widget
            st.session_state.step2_multiselect = []

        # --- CALLBACK LOGIC END ---
        
        final_cards_list = []
        
        for i, card in enumerate(st.session_state.detected_cards):
            col_img, col_input = st.columns([0.15, 0.85])
            preview_data = get_card_data(card)
            with col_img:
                if preview_data and "card_images" in preview_data:
                    st.image(preview_data["card_images"][0]["image_url_small"], use_container_width=True)
                else:
                    st.write("🖼️")
            with col_input:
               # Note: We update the list 'live' based on text input changes? 
               # For now, we trust the final "Confirm" button to gather these inputs.
               # BUT: If we change the card name here, it should ideally update the session state too?
               # Let's keep the existing logic where "final_cards_list" gathers the valid text inputs.
               new_name = st.text_input(f"Carta #{i+1}", value=card, key=f"card_{i}", label_visibility="collapsed")
               if new_name.strip():
                   final_cards_list.append(new_name)
               
               # Add a "Remove" button per card? (Out of scope for now, but good for future)

        # Dynamic Add Box
        st.multiselect(
            "Aggiungi altre carte (si sposteranno sopra dopo l'invio):", 
            options=all_card_names, 
            key="step2_multiselect",
            on_change=add_cards_callback  # This triggers the "Action"
        )
        
        st.divider()
        
        # Balanced Buttons
        col_back, col_confirm = st.columns([1, 1])
        with col_back:
            if st.button("🔙 Modifica Domanda", use_container_width=True):
                st.session_state.step = 1
                st.rerun()
                
        with col_confirm:
            if st.button("Conferma e Giudica 👨‍⚖️", type="primary", use_container_width=True):
                # Now we just need to save the edits from the text inputs
                clean_list = list(set([c.strip() for c in final_cards_list if c.strip()]))
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
            
            for idx, card_name in enumerate(st.session_state.detected_cards):
                st.write(f"🔍 Cerco: **{card_name}**...")
                card_data = get_card_data(card_name)
                
                if card_data:
                    found_cards_data.append(card_data)
                    # FIX: Add ATK/DEF/Type to context for accurate stat rulings
                    c_type = card_data.get('type', 'Unknown')
                    c_atk = f"ATK: {card_data.get('atk', '?')}" if 'Monster' in c_type else ""
                    c_def = f"DEF: {card_data.get('def', '?')}" if 'Monster' in c_type else ""
                    c_stats = f"[{c_type} | {c_atk} {c_def}]".replace("  ", " ").strip()
                    
                    cards_context += f"NOME UFFICIALE: {card_data['name']}\nDATI: {c_stats}\nTESTO AGGIORNATO: {card_data['desc']}\n\n"
                    st.success(f"✅ Trovata: {card_data['name']}")
                else:
                    missing_cards.append(card_name)
                    st.error(f"❌ Non trovata: {card_name}")
                
                if total_cards > 0:
                    progress_bar.progress((idx + 1) / total_cards)
        
        # PERSIST DATA FOR BUTTONS
        st.session_state.found_cards_cache = found_cards_data      

        # 4. Generazione Verdetto (CACHE o NUOVO)
        # MOVED OUTSIDE FOR SCOPE SAFETY
        judge_model, model_name = resolve_working_model()
        
        if not st.session_state.get("verdict_ready", False):
             with st.spinner("Generazione verdetto in corso..."):
                 
                 # RULING UFFICIALI AGGIUNTIVE
                 extra_rulings_db = """
 Q: Both players control a face-up Mirrorjade the Iceblade Dragon. Can I activate Mind Control targeting my opponent's copy of Mirrorjade? If yes, what happens when it resolves?
 A: You can activate Mind Control. If you still control a face-up Mirrorjade when Mind Control resolves, you take control of your opponent's Mirrorjade, and it is then immediately destroyed.
                 
 Q: I control a face-up Mirrorjade the Iceblade Dragon. Can I use Polymerization to Fusion Summon another copy of Mirrorjade the Iceblade Dragon, using the copy on my field as material?
 A: No, you cannot. You can only control 1 face-up "Mirrorjade the Iceblade Dragon", and cannot attempt to Summon another copy if you already do.
 
 Q: If Mirrorjade's Quick Effect is negated, or its activation is negated, can that Mirrorjade use that effect again the next turn?
 A: Yes. This card cannot use this effect next turn is part of Mirrorjade's effect. If Mirrorjade's effect, or its activation, is negated, the entire effect is not applied, including that part.
 
 Q: I activate Mirrorjade's Quick Effect. In response, the effect of my opponent's Destiny HERO - Destroyer Phoenix Enforcer resolves, destroying both it and another card on my field. If Mirrorjade is the only monster on the field when its Quick Effect resolves, what happens?
 A: When Mirrorjade's effect resolves, you must attempt to banish a monster on the field. If Mirrorjade is the only monster on the field that you can attempt to banish, you must banish Mirrorjade itself.
 """
     
                 prompt_ruling = f"""
                 Sei un **HEAD JUDGE UFFICIALE DI YU-GI-OH** (Livello 3).
                 Il tuo compito è emettere ruling tecnici estremamente precisi e pignoli.
         
                REGOLAMENTO CRITICO (PSCT - Problem Solving Card Text):
                - **ALGORITMO PUNTEGGIATURA**: Scansiona il testo carattere per carattere. Cerchi i "due punti" (:).
                - **SE C'È IL DUE PUNTI (:)**: L'effetto SI ATTIVA (Starts a Chain). È un effetto Innescato o Rapido. NON è inerente. (Esempio: "If you control...: You can Special Summon...").
                - **SE NON C'È**: Solo se mancano sia : che ; allora è un'Evocazione Inerente (Non-Activated).
                - **Damage Step**: Sii ESTREMAMENTE severo. Solo carte che modificano direttamente ATK/DEF, Counter Traps, o effetti che negano specificamente *l'attivazione* (non l'effetto) possono essere attivate qui.
                - **Condizioni di Gioco (Game State)**: Verifica sempre se l'azione è permessa dallo stato attuale del gioco.
                - **Statistiche & Floodgate**: PRIMA di giudicare, calcola l'ATK/DEF attuale considerando Magie/Trappole continue in campo (es: carte che aumentano ATK). Controlla se esistono Floodgate attivi (es: "Super Starslayer TY-PHON - Sky Crisis", "Bagooska") che inibiscono l'attivazione in base a queste stats *modificate*.
         
                 TESTI UFFICIALI (Fonte di Verità):
                 ---
                 {cards_context}
                 ---
                 
                 DATABASE RULING EXTRA (PRECEDENZA ASSOLUTA):
                 {extra_rulings_db}
                 ---
         
                 SCENARIO UTENTE:
                 "{st.session_state.question_text}"
                 
                 ISTRUZIONI:
                 1. Analizza lo scenario cercando cavilli legali.
                 2. Se la mossa è illegale, dillo chiaramente.
                 3. RAGIONA PASSO-PASSO prima di rispondere.
                 
                 FORMATO RISPOSTA RICHIESTO:
                 Devi dividere la risposta in due parti separate da una riga con scritto esattamente "---DETTAGLI---".
                 
                 Parte 1 (Prima di ---DETTAGLI---):
                 - Risposta diretta e concisa (es: "Sì, legale" oppure "No, mossa illegale").
                 
                 ---DETTAGLI---
                 
                 Parte 2 (Dopo ---DETTAGLI---):
                 - Analisi tecnica step-by-step.
                 - Cita le regole del Damage Step se rilevante.
                 """
                 
                 response = get_gemini_response(judge_model, prompt_ruling)
                 
                 if "---DETTAGLI---" in response:
                     short_answer, deep_dive = response.split("---DETTAGLI---")
                 else:
                     short_answer = response
                     deep_dive = "Nessun dettaglio tecnico aggiuntivo fornito."
                     
                 # SALVA IN SESSION STATE
                 st.session_state.verdict_short = short_answer
                 st.session_state.verdict_deep = deep_dive
                 st.session_state.verdict_ready = True
                 
        # LEGGI DA SESSION STATE
        short_answer = st.session_state.verdict_short
        deep_dive = st.session_state.verdict_deep
    
        st.success(f"Verdetto Rapido (Model: {model_name}):")
        st.markdown(short_answer)
        
        with st.expander("🧐 Spiegazione Tecnica Approfondita"):
            st.markdown(deep_dive.strip())

        # --- CHAT CONTESTUALE ---
        st.divider()
        st.markdown("### 💬 Chiedi chiarimenti")
        
        # Display Chat History
        for msg in st.session_state.judge_chat_history:
            role = "user" if msg["role"] == "user" else "assistant"
            with st.chat_message(role):
                st.markdown(msg["content"])

        # Input
        if detail_prompt := st.chat_input("Dubbi? Chiedi al Judge (ricorda il contesto)..."):
            # Aggiungi a history e visualizza subito
            st.session_state.judge_chat_history.append({"role": "user", "content": detail_prompt})
            with st.chat_message("user"):
                st.markdown(detail_prompt)
            
            # Genera risposta
            with st.chat_message("assistant"):
                with st.spinner("Consultando il regolamento..."):
                    context_full = f"""
                    CONTESTO CARTE:
                    {cards_context}
                    
                    VERDETTO PRECEDENTE:
                    {short_answer}
                    {deep_dive}
                    
                    DOMANDA UTENTE:
                    {detail_prompt}
                    """
                    followup_resp = get_gemini_response(judge_model, context_full)
                    st.markdown(followup_resp)
                    st.session_state.judge_chat_history.append({"role": "assistant", "content": followup_resp})

        # --- ACTIONS FOOTER ---
        st.divider()
        col_res, col_new = st.columns([1, 1])
        
        with col_res:
            if st.button("🔍 Consulta YGO Resources (OCG)", use_container_width=True):
                    # Logic for YGO Resources
                    cards_to_check = st.session_state.get("found_cards_cache", [])
                    if not cards_to_check and st.session_state.question_text:
                        if len(st.session_state.question_text) < 40:
                             cards_to_check = [{"name": st.session_state.question_text}]
                    
                    if cards_to_check:
                         with st.spinner("Cercando rulings OCG..."):
                             try:
                                 import importlib
                                 import yugioh_scraper
                                 importlib.reload(yugioh_scraper)
                                 from yugioh_scraper import YuGiOhMetaScraper
                                 scraper = YuGiOhMetaScraper()
                             except Exception as e:
                                 scraper = None
                                 # st.error(f"Errore scraper: {e}")
                                 
                             if scraper:
                                 # Initialize these for the loop
                                 found_rulings = []
                                 all_card_names_simple = [c["name"].split(',')[0].strip().lower() for c in cards_to_check]
                                 status_text = st.empty() # Placeholder for status messages
                                 
                                 for i, card in enumerate(cards_to_check[:3]):
                                    card_name = card["name"]
                                    # Simplify current card name too for self-exclusion logic
                                    card_simple = card_name.split(',')[0].strip().lower()
                                    
                                    status_text.info(f"⏳ Cerco ruling OCG per: **{card_name}**... ({i+1}/{len(cards_to_check[:3])})")
                                    
                                    try:
                                        # Modified Scraper returns (text, log) tuple
                                        # Pass other cards as keywords for Deep Clicking
                                        other_cards_simple = [n for n in all_card_names_simple if n != card_simple]
                                        
                                        text_res, debug_log_res = scraper.search_ygoresources_ruling(
                                            card_name, 
                                            cross_ref_keywords=other_cards_simple if len(cards_to_check) > 1 else None
                                        )
                                        
                                        if text_res:
                                            # 4. CROSS-REFERENCE FILTERING
                                            if len(cards_to_check) > 1:
                                                # We want lines that mention ANY of the OTHER cards (simplified names)
                                                other_cards_simple = [n for n in all_card_names_simple if n != card_simple]
                                                
                                                if any(other in text_res.lower() for other in other_cards_simple):
                                                     found_rulings.append(f"**{card_name}** (Found interactions):\n{text_res}")
                                                else:
                                                     pass

                                            else:
                                                found_rulings.append(f"**{card_name}**:\n{text_res}")
                                        else:
                                            print(f"DEBUG: Scraper returned None for {card_name}")
                                                
                                    except Exception as e:
                                        print(f"Skip {card_name}: {e}")
                                        debug_log_res = f"Exception: {e}"

                                 status_text.empty()
                                 
                                 if found_rulings:
                                     st.info("📜 **Rulings OCG Trovati (Cross-References):**")
                                     final_ruling_text = "\n\n".join(found_rulings)
                                     st.code(final_ruling_text, language="text")
                                     
                                     # --- NEW: AUTO-REEVALUATION ---
                                     st.markdown("### 🧠 Rivalutazione con Ruling OCG...")
                                     with st.spinner("Il Giudice sta rileggendo il caso alla luce dei nuovi ruling..."):
                                         try:
                                             # Re-construct context from session state
                                             cards_context_reval = ""
                                             cached_cards = st.session_state.get("found_cards_cache", [])
                                             for c in cached_cards:
                                                  cards_context_reval += f"NOME UFFICIALE: {c['name']}\nTESTO: {c['desc']}\n\n"
                                             
                                             judge_model, model_name = resolve_working_model()
                                             
                                             reval_prompt = f"""
                                             SEI UN HEAD JUDGE DI YU-GI-OH.
                                             
                                             SITUAZIONE PRECEDENTE:
                                             Hai dato un verdetto su una domanda dell'utente.
                                             Tuttavia, sono stati appena trovati dei **RULING UFFICIALI OCG (Giapponesi)** specifici per questo caso.
                                             
                                             I ruling OCG hanno la precedenza tecnica su qualsiasi logica generale.
                                             
                                             TESTO CARTE:
                                             {cards_context_reval}
                                             
                                             NUOVI RULING TROVATI (EVIDENZA CRITICA):
                                             ---
                                             {final_ruling_text}
                                             ---
                                             
                                             DOMANDA UTENTE:
                                             "{st.session_state.question_text}"
                                             
                                             COMPITO:
                                             1. Leggi attentamente i nuovi ruling trovati.
                                             2. Se contraddicono la tua logica precedente, AMMETTILO e correggi il verdetto.
                                             3. Se confermano la tua logica, usali come prova definitiva.
                                             4. Fornisci un verdetto finale SINTETICO ma TECNICO.
                                             
                                             FORMATO RISPOSTA:
                                             "Verdetto Aggiornato: [Sì/No/Dipende]"
                                             "Spiegazione: [Spiegazione tecnica citando il ruling]"
                                             """
                                             
                                             reval_response = judge_model.generate_content(reval_prompt)
                                             
                                             st.success("Verdetto Aggiornato (Basato su OCG):")
                                             st.write(reval_response.text)
                                             st.toast("Verdetto aggiornato con successo!")
                                             
                                         except Exception as reval_e:
                                             st.error(f"Errore durante la rivalutazione: {reval_e}")




elif mode == "📊 Meta Analyst":
    st.title("Meta Analyst 📊")
    st.markdown("### Analisi Trend, Top Cut e Decklist")

    # --- FASE 1: Download Dati ---
    if "meta_context" not in st.session_state:
        st.session_state.meta_context = ""
        st.session_state.meta_last_update = None

    # --- SIDEBAR: Selezione Fonte ---
    st.sidebar.header("Fonte Dati Meta")
    meta_source = st.sidebar.radio("Seleziona Sito:", ["YGOProDeck (TCG)", "YuGiOhMeta (Sperimentale)"])

    col1, col_status = st.columns([3, 1])
    
    with col1:
        # Title is already at the top, just show the specific source info
        # st.subheader(f"Fonte: {meta_source}") # REMOVED REDUNDANT HEADER
        
        
        # ==========================================
        # MODALITÀ: YGOProDeck (Principale)
        # ==========================================
        if meta_source == "YGOProDeck (TCG)":
            
            PROGRESS_FILE = "meta_scraping_progress.json"
            
            # --- PERSISTENCE: AUTO-LOADER (Survives App Restart/Crash) ---
            if "batch_active" not in st.session_state:
                if os.path.exists(PROGRESS_FILE):
                    try:
                        with open(PROGRESS_FILE, 'r') as f:
                            saved_data = json.load(f)
                        st.session_state.batch_queue = saved_data.get("queue", [])
                        st.session_state.batch_results = saved_data.get("results", [])
                        st.session_state.batch_logs = saved_data.get("logs", [])
                        st.session_state.batch_total_count = saved_data.get("total", 0)
                        st.session_state.batch_active = True
                        st.toast(f"🔄 Sessione ripristinata dal disco: {len(st.session_state.batch_queue)} tornei rimanenti.")
                    except Exception as e:
                        st.error(f"Errore lettura salvataggio: {e}")
                else:
                    st.session_state.batch_active = False # Default

            # --- BATCH PROCESSING STATE INITIALIZATION ---
            if "batch_queue" not in st.session_state:
                st.session_state.batch_queue = []
            if "batch_results" not in st.session_state:
                st.session_state.batch_results = []
            if "batch_active" not in st.session_state:
                st.session_state.batch_active = False
            if "batch_logs" not in st.session_state:
                st.session_state.batch_logs = []
            if "batch_total_count" not in st.session_state:
                st.session_state.batch_total_count = 0

            # --- ACTION: START DISCOVERY (PHASE 1) ---
            if not st.session_state.batch_active:
                if st.button("🔄 Scansiona Nuovi Tornei", type="primary"):
                    with st.spinner("🔍 Fase 1: Ricerca Tornei Recent (Playwright)..."):
                        try:
                            # 1. Discovery
                            scraper_tool = YuGiOhMetaScraper()
                            with st.status("🔍 Avvio Discovery...", expanded=True) as status:
                                found_links = scraper_tool.get_ygoprodeck_tournaments(days_lookback=60) # Reduced to 30 for safety
                                status.update(label=f"✅ Trovati {len(found_links)} tornei!", state="complete")
                            
                            if found_links:
                                # Prepare Queue
                                urls_unique = set()
                                queue = []
                                for t_obj in found_links:
                                    # Normalized check
                                    link = t_obj['url'] if isinstance(t_obj, dict) else t_obj
                                    if link not in urls_unique:
                                        urls_unique.add(link)
                                        # Serialization Helper: Convert datetime to ISO string instantly
                                        if isinstance(t_obj, dict):
                                            serializable_obj = t_obj.copy()
                                            if "date" in serializable_obj and (isinstance(serializable_obj["date"], datetime) or isinstance(serializable_obj["date"], date)):
                                                serializable_obj["date"] = serializable_obj["date"].isoformat()
                                            queue.append(serializable_obj)
                                        else:
                                            queue.append({"url": link, "name": link}) # Fallback
                                
                                st.session_state.batch_queue = queue
                                st.session_state.batch_total_count = len(queue)
                                st.session_state.batch_results = [] # Clear previous
                                st.session_state.batch_logs = ["✅ Discovery completata."]
                                st.session_state.batch_active = True
                                
                                # SAVE TO DISK IMMEDIATELY
                                with open(PROGRESS_FILE, 'w') as f:
                                    json.dump({
                                        "queue": st.session_state.batch_queue,
                                        "results": [],
                                        "logs": st.session_state.batch_logs,
                                        "total": st.session_state.batch_total_count
                                    }, f)

                                st.rerun() # START THE LOOP
                            else:
                                st.warning("⚠️ Nessun torneo trovato negli ultimi 30 giorni.")
                        
                        except Exception as e:
                            st.error(f"Errore Discovery: {e}")

            # --- ACTION: BATCH PROCESSING LOOP (PHASE 2) ---
            else:
                # Progress UI
                total = st.session_state.batch_total_count
                remaining = len(st.session_state.batch_queue)
                processed = total - remaining
                progress = processed / total if total > 0 else 0
                
                st.progress(progress, text=f"📥 Scaricamento Dati: {processed}/{total} tornei completati...")
                
                # STOP BUTTON
                if st.button("⛔ Interrompi e Cancella"):
                    st.session_state.batch_active = False
                    if os.path.exists(PROGRESS_FILE):
                         os.remove(PROGRESS_FILE)
                    st.warning("Scansione annullata e file temporanei rimossi.")
                    st.rerun()

                # PROCESS BATCH
                if remaining > 0:
                    BATCH_SIZE = 1 # Process one by one (User Request)
                    batch = st.session_state.batch_queue[:BATCH_SIZE]
                    st.session_state.batch_queue = st.session_state.batch_queue[BATCH_SIZE:] # Pop
                    
                    with st.spinner(f"Elaborazione blocco di {len(batch)} tornei..."):
                        # Process ONLY this batch
                        try:
                            # Re-use the existing logic logic, but scoped
                             processed_batch = []
                             tasks = []
                             
                             # Pre-process batch items
                             for idx, t_obj in enumerate(batch):
                                 # (Simplifying extraction logic here for brevity, keeping core fields)
                                 # We need to deeply scrape these.
                                 # Wait, t_obj is just metadata (url, name, etc.)
                                 # We need to Visit the tournament page to get deck links
                                 # AND then scrape the decks.
                                 # This double-scrape is heavy.
                                 
                                 # TRICK: To avoid complex parsing of the tournament page AGAIN which was heavy,
                                 # we should rely on what we did before?
                                 # No, before we did: Discovery -> List of Tournament URLs
                                 # Then: Request(TournamentURL) -> Parse Rows -> Threads(DeckURL).
                                 
                                 # We must do that here.
                                 url = t_obj['url'] if isinstance(t_obj, dict) else t_obj
                                 tourney_name = t_obj.get('name', 'Unknown') if isinstance(t_obj, dict) else url
                                 
                                 try:
                                     HEADERS = {'User-Agent': 'Mozilla/5.0'}
                                     resp = requests.get(url, headers=HEADERS, timeout=10)
                                     soup = BeautifulSoup(resp.text, 'html.parser')
                                     
                                     # Extract Decks
                                     # (Reuse core logic logic efficiently)
                                     div_table = soup.find('div', {'id': 'tournament_table'})
                                     if div_table:
                                         rows = div_table.find_all(['a', 'div'], class_='tournament_table_row')
                                         for r_i, row in enumerate(rows):
                                              # Minimal Extraction for Task
                                              cells = row.find_all('span', class_='as-tablecell')
                                              if len(cells) >= 3:
                                                  deck_cell = cells[2]
                                                  link_tag = deck_cell.find('a')
                                                  deck_link = row.get('href') if row.name == 'a' else (link_tag.get('href') if link_tag else None)
                                                  
                                                  if deck_link and "deck/" in deck_link:
                                                      # Store Task: (TournamentMeta, DeckLink, Place/Player info needed?)
                                                      # We need full info.
                                                      # Let's extract basic info quickly
                                                      place = cells[0].get_text(strip=True)
                                                      player = cells[1].get_text(strip=True)
                                                      deck_name = deck_cell.get_text(strip=True)
                                                      
                                                      # Add to ThreadPool Tasks
                                                      tasks.append({
                                                          "url": deck_link,
                                                          "meta": t_obj,
                                                          "place": place,
                                                          "player": player,
                                                          "deck_name": deck_name,
                                                          "event_source": tourney_name
                                                      })
                                 except Exception as e_req:
                                     st.session_state.batch_logs.append(f"❌ Errore Torneo {tourney_name}: {e_req}")

                            # EXECUTE BATCH TASKS (Decks)
                             if tasks:
                                 with ThreadPoolExecutor(max_workers=2) as executor:
                                     future_to_item = {executor.submit(scrape_deck_list, t["url"]): t for t in tasks}
                                     
                                     for future in as_completed(future_to_item):
                                         item_ctx = future_to_item[future]
                                         try:
                                             content, raw_main, raw_side, raw_extra = future.result()
                                             if content:
                                                 # Build Final Object
                                                 final_obj = {
                                                     "place": item_ctx["place"],
                                                     "player": item_ctx["player"],
                                                     "deck_text": item_ctx["deck_name"],
                                                     "link": item_ctx["url"],
                                                     "details": f"\n   [DETTAGLIO DECK]\n   {content.replace(chr(10), chr(10)+'   ')}\n",
                                                     "event_source": item_ctx["event_source"],
                                                     "country": item_ctx["meta"].get("country", "Unknown"),
                                                     "event_type": item_ctx["meta"].get("type", "Other"),
                                                     "players": item_ctx["meta"].get("players", 0),
                                                     "raw_main": raw_main,
                                                     "raw_side": raw_side,
                                                     "raw_extra": raw_extra
                                                 }
                                                 processed_batch.append(final_obj)
                                         except: pass
                                         
                             # APPEND TO SESSION
                             st.session_state.batch_results.extend(processed_batch)
                             st.session_state.batch_logs.append(f"✅ Processato blocco: {len(batch)} tornei, {len(processed_batch)} mazzi estratti.")
                             
                             # FORCE GC
                             gc.collect()
                             
                             # SAVE PROGRESS TO DISK (CRITICAL PROTECTION)
                             with open(PROGRESS_FILE, 'w') as f:
                                    json.dump({
                                        "queue": st.session_state.batch_queue,
                                        "results": st.session_state.batch_results,
                                        "logs": st.session_state.batch_logs,
                                        "total": st.session_state.batch_total_count
                                    }, f)
                             
                        except Exception as e_batch:
                             st.session_state.batch_logs.append(f"❌ Errore critico nel blocco: {e_batch}")
                    
                    # RERUN TO NEXT BATCH
                    time.sleep(0.5) # Yield
                    st.rerun()

                else:
                    # --- FINALIZATION (Queue Empty) ---
                    st.success("✅ Download Completato!")
                    
                    # 1. Aggregate
                    all_processed_items_global = st.session_state.batch_results
                    
                    # 2. Build Context
                    premier_text = "=== 🏆 PREMIER EVENTS (YCS, WCQ, CHAMPIONSHIPS) ===\n"
                    regional_text = "=== 🌍 REGIONAL / MAJOR EVENTS ===\n"
                    other_text = "=== 🏠 LOCALS / OTHER ===\n"
                    
                    for item in all_processed_items_global:
                        source = item.get('event_source', '').lower()
                        entry = f"- {item.get('place','?')}: {item.get('player','?')} -> {item.get('deck_text','?')} (Event: {item.get('event_source','?')}){item.get('details','')}\n"
                        
                        if "ycs" in source or "championship" in source or "wcq" in source:
                            premier_text += entry
                        elif "regional" in source or "major" in source:
                            regional_text += entry
                        else:
                            other_text += entry
                    
                    aggregated_text = f"DATA REPORT: {datetime.now().strftime('%d %B %Y')}\nFONTE: YGOProDeck (Recenti)\n\n" + f"\n{premier_text}\n{regional_text}\n{other_text}"
                    
                    st.session_state.meta_context = aggregated_text
                    st.session_state.meta_last_update = datetime.now().strftime("%H:%M")
                    
                    # 3. Build Stats
                    from collections import Counter
                    all_decks_found = [item['deck_text'] for item in all_processed_items_global if item.get('deck_text') and item['deck_text'].strip()]
                    deck_counts = Counter(all_decks_found)
                    structured_data = [{"name": k, "count": v} for k, v in deck_counts.items()]
                    st.session_state.meta_structured_data = structured_data
                    st.session_state.meta_all_items_global = all_processed_items_global
                    
                    # 4. Reset & Cleanup
                    with st.expander("📝 Log Scansione"):
                        for l in st.session_state.batch_logs: st.write(l)
                        
                    if st.button("Pulisci e Riavvia"):
                         st.session_state.batch_active = False
                         st.session_state.batch_queue = []
                         st.session_state.batch_results = []
                         if os.path.exists(PROGRESS_FILE):
                             os.remove(PROGRESS_FILE)
                         st.rerun()
        
        # --- PERSISTENT DASHBOARD RENDERER (Runs on every reload) ---
        if "meta_structured_data" in st.session_state and st.session_state.meta_structured_data:
            st.divider()
            st.subheader("📊 Analisi Dati Meta")
            
            all_items = st.session_state.get("meta_all_items_global", [])
            
            # --- FILTERS UI (MOVED TO TOP) ---
            st.markdown("### 🌪️ Filtri Ispezione")
            f_col1, f_col2, f_col3 = st.columns(3)
            
            # 1. Extract Countries & Types
            all_countries = sorted(list(set([i.get('country', 'Unknown') for i in all_items])))
            all_types = sorted(list(set([i.get('event_type', 'Other') for i in all_items])))
            
            # Fix for potential 0 max_players causing Slider Error
            p_counts = [i.get('players', 0) for i in all_items]
            max_players = max(p_counts) if p_counts and max(p_counts) > 0 else 100
            
            with f_col1:
                sel_countries = st.multiselect("🌍 Paese", options=all_countries, default=[]) # Empty default = All
            with f_col2:
                sel_types = st.multiselect("🏆 Tipo Evento", options=all_types, default=[]) # Empty default = All
            with f_col3:
                min_p = st.slider("👥 Min. Players", 0, max_players, 0, step=10)
            
            # FILTER LOGIC
            filtered_items = []
            for item in all_items:
                # Logic: If list is empty, treat as "All Selected". Else, check existence.
                country_match = (not sel_countries) or (item.get('country', 'Unknown') in sel_countries)
                type_match = (not sel_types) or (item.get('event_type', 'Other') in sel_types)
                player_match = item.get('players', 0) >= min_p
                
                if country_match and type_match and player_match:
                    filtered_items.append(item)
            
            st.caption(f"Mostrando {len(filtered_items)} su {len(all_items)} mazzi.")
            st.divider()

            # --- REACTIVE STATS (CALCULATED ON FILTERED ITEMS) ---
            from collections import Counter
            
            if not filtered_items:
                 st.info("💡 Nessun dato locale. Avvia la scansione per iniziare.") # CLEANER EMPTY STATE
            else:
                 # 1. TOP 4 PERFORMING DECKS (REACTIVE)
                 # Filter out empty strings/whitespace
                 all_decks_found = [item['deck_text'] for item in filtered_items if item.get('deck_text') and item['deck_text'].strip()]
                 deck_counts = Counter(all_decks_found)
                 
                 structured_data = [{"name": k, "count": v} for k, v in deck_counts.items()]
                 sorted_decks = sorted(structured_data, key=lambda x: x['count'], reverse=True)
                 top_4 = sorted_decks[:4]
                 
                 col_top, col_conv = st.columns(2)
                 
                 with col_top:
                     st.write("#### 🏆 Top 4 Mazzi (Filtrati)")
                     for i, d in enumerate(top_4):
                         st.write(f"**#{i+1} {d['name']}** - {d['count']} Top")
                         
                 # 2. BEST CONVERSION (Top 6 REACTIVE)
                 top_6_names = [d['name'] for d in sorted_decks[:6]]
                 best_conversion_deck = None
                 best_rate = -1.0
                 conversion_stats = {}
                 
                 # Calc stats on filtered items
                 for item in filtered_items:
                     d_name = item.get('deck_text')
                     if not d_name or not d_name.strip(): continue
                     
                     p_text = item.get('place', '').lower()
                     is_winner = "winner" in p_text or "1st" in p_text
                     
                     if d_name not in conversion_stats: conversion_stats[d_name] = {"wins": 0, "total": 0}
                     conversion_stats[d_name]["total"] += 1
                     if is_winner: conversion_stats[d_name]["wins"] += 1
                 
                 # Find best rate among top 6
                 for d_name, stats in conversion_stats.items():
                      if d_name in top_6_names: 
                          if stats["total"] > 0:
                              rate = stats["wins"] / stats["total"]
                              if rate > best_rate:
                                  best_rate = rate
                                  best_conversion_deck = d_name
                 
                 with col_conv:
                     st.write("#### 🎯 Best Converter (Tra i Top 6 Filtrati)")
                     if best_conversion_deck:
                         stats = conversion_stats[best_conversion_deck]
                         pct = int(best_rate * 100)
                         st.success(f"**{best_conversion_deck}**")
                         st.caption(f"Winrate **{pct}%** ({stats['wins']}/{stats['total']} Top).")
                     else:
                         st.info("Nessun vincitore trovato tra i Top 6 mazzi filtrati.")

            # --- 3. TECH & STAPLE ANALYSIS (NEW) ---
            # --- 3. TECH & STAPLE ANALYSIS (NEW) ---
            st.divider()
            st.markdown("### 📉 Analisi Tech & Staple (No AI)")
            st.caption("Statistiche calcolate in tempo reale sui mazzi filtrati.")
            
            # Helper to count cards
            # items have 'raw_main', 'raw_side', 'raw_extra'
            
            # BUGFIX: Only count decks that actully have a list!
            valid_items = [i for i in filtered_items if i.get("raw_main")]
            total_decks = len(valid_items)
            
            if total_decks > 0:
                main_counts = {} # name -> count of DECKS containing it (not total copies)
                side_counts = {}
                extra_counts = {}
                
                # We want representation % (Usage Rate)
                # i.e. "Ash Blossom" is in 80% of decks.
                
                for item in valid_items:
                    # Helper for extraction
                    def extract_unique_names(raw_list):
                        names = set()
                        for c_entry in raw_list:
                            c_name = c_entry.get("card", {}).get("name")
                            if c_name: names.add(c_name)
                        return names

                    # Main
                    for c in extract_unique_names(item.get("raw_main", [])):
                        main_counts[c] = main_counts.get(c, 0) + 1
                        
                    # Side
                    for c in extract_unique_names(item.get("raw_side", [])):
                        side_counts[c] = side_counts.get(c, 0) + 1
                        
                    # Extra
                    for c in extract_unique_names(item.get("raw_extra", [])):
                        extra_counts[c] = extra_counts.get(c, 0) + 1
                
                # Sort by frequency
                sorted_main = sorted(main_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                sorted_side = sorted(side_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                sorted_extra = sorted(extra_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                
                # CSS to Hide Toolbar for a specialized minimal look
                st.markdown("""
                <style>
                [data-testid="stElementToolbar"] {
                    display: none;
                }
                </style>
                """, unsafe_allow_html=True)
                
                # Helper for DataFrame
                def create_stat_df(sorted_data, total):
                    data = []
                    for name, count in sorted_data:
                        pct = (count / total) * 100
                        # FORMAT: Strigified percentage for cleaner look
                        data.append({"Carta": name, "%": f"{int(pct)}%"}) 
                    return pd.DataFrame(data)

                # --- VERTICAL EXPANDER LAYOUT ---
                
                with st.expander("⚔️ Top Main Deck", expanded=False):
                    df_main = create_stat_df(sorted_main, total_decks)
                    st.dataframe(
                        df_main,
                        hide_index=True,
                        use_container_width=True
                    )

                with st.expander("🛡️ Top Side Deck", expanded=False):
                    df_side = create_stat_df(sorted_side, total_decks)
                    st.dataframe(
                        df_side,
                        hide_index=True,
                        use_container_width=True
                    )
                        
                with st.expander("🟣 Top Extra Deck", expanded=False):
                    df_extra = create_stat_df(sorted_extra, total_decks)
                    st.dataframe(
                        df_extra,
                        hide_index=True,
                        use_container_width=True
                    )

                # --- 4. AUTOCOMPLETE SEARCH ---
                st.divider()
                st.markdown("#### 🔎 Cerca Percentuale Carta")
                
                # Collect ALL unique card names for the dropdown
                all_card_names = sorted(list(set(list(main_counts.keys()) + list(side_counts.keys()) + list(extra_counts.keys()))))
                
                search_card = st.selectbox(
                    "Seleziona una carta per vedere le statistiche:",
                    options=[""] + all_card_names,
                    index=0,
                    placeholder="Digita il nome della carta..."
                )

                if search_card:
                     m_count = main_counts.get(search_card, 0)
                     s_count = side_counts.get(search_card, 0)
                     e_count = extra_counts.get(search_card, 0)
                     
                     m_pct = int((m_count / total_decks) * 100)
                     s_pct = int((s_count / total_decks) * 100)
                     e_pct = int((e_count / total_decks) * 100)
                     
                     res_col1, res_col2, res_col3 = st.columns(3)
                     res_col1.metric("Main Deck", f"{m_pct}%")
                     res_col2.metric("Side Deck", f"{s_pct}%")
                     res_col3.metric("Extra Deck", f"{e_pct}%")
                         
            else:
                st.info("Nessun dato grezzo disponibile per l'analisi Tech. Prova ad aggiornare il database.")

            # --- INTERACTIVE DECK INSPECTOR ---
            st.subheader("🔍 Ispeziona Decklist")
            st.caption("Seleziona un giocatore/mazzo per vedere la lista completa.")
            
            deck_map = {}
            for item in filtered_items:
                # Re-build label - USER REQUESTED FORMAT
                # "YCS Bologna (Italy) | 1st Place | Nome player | nome deck"
                event_name = item.get('event_source', 'Event').split(" - ")[0] 
                place = item.get('place', 'N/A')
                country = item.get('country', 'Global')
                player = item.get('player', 'Unknown')
                deck = item.get('deck_text', 'Unknown Deck')
                
                # NEW FORMAT: Event | Country | Place | Player | Deck
                label = f"{event_name} | {country} | {place} | {player} | {deck}"
                deck_map[label] = item
            
            selected_label = st.selectbox("Scegli Decklist:", options=list(deck_map.keys()), index=None, placeholder="Cerca un mazzo...")
            if selected_label:
                item = deck_map[selected_label]
                with st.expander(f"📂 Lista Carte: {item['deck_text']} ({item['player']})", expanded=False):
                    col_head1, col_head2 = st.columns([3, 1])
                    col_head1.markdown(f"**Evento:** {item.get('event_source', 'N/A')}")
                    col_head2.markdown(f"[🔗 Apri su YGOProDeck]({item['link']})")
                    
                    if item['details']:
                        # PARSE & VISUALIZE DECK
                        import re
                        
                        raw_text = item['details'].replace("[DETTAGLIO DECK]", "").strip()
                        
                        # Regex to find: "3x Name <URL>"
                        sections = {"Main Deck": [], "Extra Deck": [], "Side Deck": []}
                        current_section = "Main Deck"
                        
                        lines = raw_text.split('\n')
                        for line in lines:
                            line = line.strip()
                            if not line: continue
                            
                            if "**Main Deck**" in line: 
                                current_section = "Main Deck"; continue
                            elif "**Extra Deck**" in line: 
                                current_section = "Extra Deck"; continue
                            elif "**Side Deck**" in line: 
                                current_section = "Side Deck"; continue
                            
                            matches = re.findall(r"(\d+)x\s(.*?)\s<(https?://[^>]+)>", line)
                            for count, name, url in matches:
                                try:
                                    cnt = int(count)
                                    # Multiply images by count for grid view
                                    for _ in range(cnt):
                                        sections[current_section].append({"name": name, "url": url})
                                except: pass
                        
                        # RENDER GRID
                        if "card_db" not in st.session_state:
                             st.session_state.card_db = load_card_database()
                        db = st.session_state.card_db

                        for sec_name, cards in sections.items():
                            if cards:
                                
                                # 1. MAIN DECK & SIDE DECK: Split by Type
                                if sec_name in ["Main Deck", "Side Deck"]:
                                    monsters = []
                                    spells = []
                                    traps = []
                                    
                                    for card in cards:
                                        c_type = db.get(card['name'], "Monster") # Default to Monster
                                        if "Spell" in c_type: spells.append(card)
                                        elif "Trap" in c_type: traps.append(card)
                                        else: monsters.append(card)
                                    
                                    # Render Sub-grids with Headers
                                    sub_sections = [("Mostri", monsters), ("Magie", spells), ("Trappole", traps)]
                                    
                                    st.markdown(f"##### {sec_name} ({len(cards)})")
                                    for sub_name, sub_cards in sub_sections:
                                        if sub_cards:
                                            st.markdown(f"**{sub_name}** ({len(sub_cards)})")
                                            cols = st.columns(8)
                                            for i, card in enumerate(sub_cards):
                                                col_idx = i % 8
                                                with cols[col_idx]:
                                                    st.image(card['url'], use_column_width=True)
                                
                                # 2. EXTRA DECK: Sort by Type (Fused together)
                                elif sec_name == "Extra Deck":
                                    # Custom Sort Order
                                    def get_extra_sort_index(card):
                                        c_type = db.get(card['name'], "").lower()
                                        if "fusion" in c_type: return 0
                                        if "synchro" in c_type: return 1
                                        if "xyz" in c_type: return 2
                                        if "link" in c_type: return 3
                                        return 4
                                    
                                    cards.sort(key=get_extra_sort_index)
                                    
                                    st.markdown(f"##### {sec_name} ({len(cards)})")
                                    cols = st.columns(8)
                                    for i, card in enumerate(cards):
                                        col_idx = i % 8
                                        with cols[col_idx]:
                                            st.image(card['url'], use_column_width=True)
                                
                                else:
                                    # Fallback
                                    st.markdown(f"##### {sec_name} ({len(cards)})")
                                    cols = st.columns(8)
                                    for i, card in enumerate(cards):
                                         with cols[i % 8]:
                                             st.image(card['url'], use_column_width=True)
                        
                        # Fallback Text (Formatted for Print)
                        st.markdown("#### 📋 Copia Lista Testuale")
                        if True: # Removed nested expander
                            if "card_db" not in st.session_state:
                                 st.session_state.card_db = load_card_database()
                            db = st.session_state.card_db
                            
                            # Re-bucket just for printing text (deduplicated)
                            from collections import Counter
                            
                            def format_section(c_list, label):
                                if not c_list: return ""
                                cnt = Counter([c['name'] for c in c_list])
                                txt = f"--- {label} ---\n"
                                for n, c in cnt.items(): txt += f"{c}x {n}\n"
                                return txt + "\n"

                            print_text = ""
                            # Main
                            m_cards = [c for c in sections["Main Deck"]]
                            monsters = [c for c in m_cards if "Spell" not in db.get(c['name'], "Monster") and "Trap" not in db.get(c['name'], "Monster")]
                            spells = [c for c in m_cards if "Spell" in db.get(c['name'], "")]
                            traps = [c for c in m_cards if "Trap" in db.get(c['name'], "")]
                            
                            print_text += format_section(monsters, "Monsters")
                            print_text += format_section(spells, "Spells")
                            print_text += format_section(traps, "Traps")
                            print_text += format_section(sections["Extra Deck"], "Extra Deck")
                            print_text += format_section(sections["Side Deck"], "Side Deck")
                            
                            st.code(print_text)

                    else:
                        st.info("Dettagli del mazzo non ancora scaricati. Riprova ad aggiornare.")

                        



        # ==========================================
        # MODALITÀ: YuGiOhMeta (Sperimentale)
        # ==========================================
        elif meta_source == "YuGiOhMeta (Sperimentale)":
            st.markdown("### 🧬 YuGiOhMeta Integration")
            
            ym_mode = st.radio("Modalità:", ["Tier List Live (Snapshot)", "Analisi Tech Competitiva (All vs T3)", "Analisi Articoli (Roundup)"], horizontal=True)
            
            # --- MODE 1: TIER LIST LIVE ---
            if ym_mode == "Tier List Live (Snapshot)":
                st.info("📊 **Tier List Mode**: Analizza lo snapshot attuale di YuGiOhMeta (Deck Types + Techs).")
                if st.button("📡 Scarica Dati Tier List", type="primary"):
                    scraper_tool = YuGiOhMetaScraper()
                    with st.status("🔍 Analizzando yugiohmeta.com...", expanded=True):
                        st.write("🌍 Navigazione verso /tier-list...")
                        data = scraper_tool.get_tier_list_data()
                        if not data["decks"]:
                            st.error("❌ Impossibile scaricare la Tier List.")
                            st.stop()
                        st.success("✅ Dati scaricati con successo!")
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.subheader("🏆 Meta Decks")
                            for d in data["decks"]: st.write(f"**{d['name']}**: {d['percent']} ({d['count']} tops)")
                        with col2:
                            st.subheader("🛠️ Main Techs")
                            with st.expander("Vedi Techs", expanded=True):
                                for t in data["techs"][:20]: st.write(f"- {t['name']} ({t['usage']})")
                        with col3:
                            st.subheader("🛡️ Side Staples")
                            with st.expander("Vedi Side", expanded=True):
                                for s in data["side"][:20]: st.write(f"- {s['name']} ({s['usage']})")
                        
                        aggregated_text = f"DATA TIER LIST: {datetime.now().strftime('%d %B %Y')}\nFONTE: YuGiOhMeta Tier List\n\n"
                        aggregated_text += f"=== DECK BREAKDOWN ===\n{str(data['decks'])}\n\n"
                        aggregated_text += f"=== MAIN DECK TECHS ===\n{str(data['techs'])}\n\n"
                        aggregated_text += f"=== SIDE DECK STAPLES ===\n{str(data['side'])}\n"
                        st.session_state.meta_context = aggregated_text
                        st.session_state.meta_last_update = datetime.now().strftime("%H:%M")
                        
                        # PERSIST STRUCTURED DATA
                        # data["decks"] is already [{'name': 'X', 'count': N, 'percent': P}]
                        # Normalize keys: 'name', 'count' (ensure int)
                        structured_data = []
                        for d in data["decks"]:
                             try:
                                 c = int(d['count'])
                             except:
                                 c = 0
                             structured_data.append({"name": d['name'], "count": c})
                        st.session_state.meta_structured_data = structured_data
                        
                        st.success("🧠 Dati inviati all'AI! Ora chiedi pure.")

            # --- MODE 2: TECH DEEP DIVE (NEW) ---
            elif ym_mode == "Analisi Tech Competitiva (All vs T3)":
                st.info("🔬 **Tech Deep Dive**: Confronta le carte più giocate nel Meta Generale vs Tornei Competitivi (T3 Events).")
                
                if st.button("🔎 Avvia Analisi Comparativa", type="primary"):
                    scraper_tool = YuGiOhMetaScraper()
                    with st.status("🕵️‍♀️ Analisi Approfondita Techs...", expanded=True):
                        st.write("🌍 Navigazione verso /tier-list#techs...")
                        data = scraper_tool.get_tech_deep_dive()
                        
                        if not data["all"] or not data["t3"]:
                            st.error("❌ Impossibile recuperare i dati comparativi.")
                            st.stop()
                            
                        st.success("✅ Dati Estratti: Events All vs T3 Only")
                        
                        # Show Comparison
                        st.subheader("⚔️ Confronto Utilizzo (Top 20)")
                        
                        # Prepare data for display
                        # Create a map for T3 stats
                        t3_map = {c["name"]: c for c in data["t3"]}
                        
                        for item in data["all"][:20]:
                            name = item["name"]
                            all_pct = item.get("percent", "N/A")
                            t3_item = t3_map.get(name)
                            t3_pct = t3_item.get("percent", "N/A") if t3_item else "N/A"
                            
                            # Visual Diff
                            diff_str = ""
                            try:
                                v1 = float(all_pct.replace('%',''))
                                v2 = float(t3_pct.replace('%',''))
                                diff = v2 - v1
                                if diff > 0: diff_str = f"📈 +{diff:.1f}% in T3"
                                elif diff < 0: diff_str = f"📉 {diff:.1f}% in T3"
                                else: diff_str = "="
                            except:
                                pass
                                
                            st.markdown(f"**{name}**: All ({all_pct}) vs T3 ({t3_pct}) | {diff_str}")
                            
                        # AI Context
                        aggregated_text = f"DATA TECH ANALYSIS: {datetime.now().strftime('%d %B %Y')}\nMODE: Tech Deep Dive (All vs T3)\n\n"
                        aggregated_text += f"=== ALL EVENTS TECHS ===\n{str(data['all'])}\n\n"
                        aggregated_text += f"=== T3 (COMPETITIVE) TECHS ===\n{str(data['t3'])}\n"
                        
                        st.session_state.meta_context = aggregated_text
                        st.session_state.meta_last_update = datetime.now().strftime("%H:%M")
                        st.success("🧠 Report Comparativo pronto per l'AI!")

            # --- MODE 3: MANUAL / ROUNDUP ---
            else:
                st.info("ℹ️ Per analizzare un torneo, incolla il link di UN MAZZO qualsiasi di quel torneo (es. 'Top Decks' -> click su un mazzo -> copia URL).")
                
                ym_urls = st.text_area("🔗 Incolla Link Mazzo/i (YuGiOhMeta):", placeholder="https://www.yugiohmeta.com/top-decks/...\nhttps://www.yugiohmeta.com/top-decks/...", height=100)
                
                if st.button("🚀 Estrai Dati Torneo"):
                    if not ym_urls:
                        st.warning("Incolla almeno un link!")
                    else:
                        scraper = YuGiOhMetaScraper()
                        # Split by newlines/commas and clean
                        raw_urls = [u.strip() for u in ym_urls.replace(",", "\n").split("\n") if u.strip()]
                        url_list = []
                        
                        # Check for Roundup URLs (Articles) and Auto-Expand
                        with st.status("🔍 Analisi Link...", expanded=True) as status:
                            for u in raw_urls:
                                if "/articles/tournaments/" in u:
                                    st.info(f"📄 Rilevata Pagina Roundup: {u}")
                                    st.write("🤖 Avvio Browser per estrarre i link dei mazzi...")
                                    try:
                                        extracted_links = scraper.get_links_from_roundup(u)
                                        if extracted_links:
                                            st.success(f"✅ Estratti {len(extracted_links)} link dalla pagina!")
                                            url_list.extend(extracted_links)
                                        else:
                                            st.error("⚠️ Nessun link trovato nella pagina roundup.")
                                    except Exception as e:
                                        st.error(f"Errore Playwright: {e}")
                                else:
                                    url_list.append(u)
                            
                            if not url_list:
                                 st.warning("Nessun link valido trovato.")
                            else:
                                status.update(label=f"Analisi di {len(url_list)} link...", state="running")
                                all_decks_data = []
                                scraped_events = set()
                                
                                progress_bar = st.progress(0)
                                
                                for idx, url in enumerate(url_list):
                                    st.write(f"🔍 Analisi Link {idx+1}/{len(url_list)}...")
                                    event_id, event_name = scraper.get_event_id_from_deck_url(url)
                                    
                                    if event_id:
                                        if event_id in scraped_events:
                                            st.warning(f"⚠️ Evento già processato: {event_name}")
                                        else:
                                            st.success(f"✅ Torneo Identificato: **{event_name}**")
                                            decks = scraper.get_tournament_decks(event_id)
                                            if decks:
                                                # Add event name to each deck for context
                                                for d in decks: d["_eventName"] = event_name
                                                all_decks_data.extend(decks)
                                                scraped_events.add(event_id)
                                    else:
                                        st.error(f"❌ Impossibile risolvere link: {url}")
                                    
                                    progress_bar.progress((idx + 1) / len(url_list))
                                
                                if all_decks_data:
                                    total_decks = len(all_decks_data)
                                    st.success(f"📦 Totale Mazzi Trovati: {total_decks}")
                                    
                                    start_time = time.time()
                                    aggregated_text = f"DATA ANALISI: {datetime.now().strftime('%d %B %Y')}\nFONTE: YuGiOhMeta\nEVENTI: {', '.join(scraped_events)}\n"
                                    
                                    # Analyze Coverage (Global)
                                    coverage_report = scraper.analyze_coverage(all_decks_data)
                                    aggregated_text += f"COVERAGE GLOBALE: {coverage_report}\n\n"
                                    st.info(coverage_report)

                                    # Processing Decks
                                    for i, deck in enumerate(all_decks_data):
                                        ename = deck.get("_eventName", "Unknown Event")
                                        parsed_deck = scraper.parse_deck_list(deck)
                                        # Add Event Name to the deck summary
                                        parsed_deck = f"Event: {ename}\n" + parsed_deck
                                        aggregated_text += f"=== DECK {i+1} ===\n{parsed_deck}\n{'='*30}\n"
                                    
                                    st.session_state.meta_context = aggregated_text
                                    st.session_state.meta_last_update = datetime.now().strftime("%H:%M")
                                    
                                    # PERSIST STRUCTURED DATA
                                    # all_decks_data contains raw deck dicts
                                    # We need to extract deckType name and count
                                    from collections import Counter
                                    deck_names = []
                                    for d in all_decks_data:
                                         d_name = d.get("deckType", {}).get("name", "Unknown Deck")
                                         deck_names.append(d_name)
                                    
                                    cnt = Counter(deck_names)
                                    structured_data = [{"name": k, "count": v} for k, v in cnt.items()]
                                    st.session_state.meta_structured_data = structured_data
                                    
                                    # PERSIST RAW ITEMS FOR TECH ANALYSIS (Global)
                                    # We need to map raw deck data to the format used by the Inspector
                                    global_items = []
                                    for d in all_decks_data:
                                        # d is the raw JSON from scraping
                                        item = {
                                            "event_source": d.get("_eventName", "Unknown Event"),
                                            "country": d.get("country", "Global"), # Check if this exists in deck dict, might need to pass it down
                                            "place": d.get("tournamentPlacement", "N/A"),
                                            "player": d.get("author", "Unknown"),
                                            "deck_text": d.get("deckType", {}).get("name", "Unknown"),
                                            "players": 0, # Not readily available in deck dict unless passed down
                                            "event_type": "Other", # Context needed
                                            "details": scraper.parse_deck_list(d), # String format for legacy viewer
                                            "link": d.get("chart", "#"), # Just a link if available or placeholder
                                            
                                            # CRITICAL: RAW DATA FOR TECH ANALYSIS
                                            "raw_main": d.get("main", []),
                                            "raw_side": d.get("side", [])
                                        }
                                        global_items.append(item)
                                    
                                    st.session_state.meta_all_items_global = global_items
                                    
                                    status.update(label="Scraping Multiplo Completato!", state="complete", expanded=False)
                                    st.success("✅ Database Meta Aggiornato con successo!")
                                else:
                                    st.error("❌ Nessun dato valido estratto dai link forniti.")

    # --- STATUS BAR COMUNE ---
    with col_status:
        if st.session_state.meta_last_update:
            st.caption(f"Ultimo aggiornamento: {st.session_state.meta_last_update}")
        else:
            st.warning("⚠️ Database vuoto.")

    st.divider()

    # --- FASE 2: Chatbot (RAG) - COMUNE ---
    # --- FASE 2: Chatbot (RAG) - COMUNE ---
    st.markdown("### 🧠 Analisi Strategica & Consigli")
    
    # CSS STYLE INJECTION FOR TOOLTIPS (Inject ONCE)
    st.markdown("""
    <style>
    /* Tooltip Container */
    .ygo-card-wrapper {
        position: relative;
        display: inline-block;
        margin: 4px;
        cursor: pointer;
    }
    .ygo-card-wrapper:hover .ygo-tooltip {
        visibility: visible;
        opacity: 1;
    }
    /* Tooltip Box */
    .ygo-tooltip {
        visibility: hidden;
        width: 250px;
        background-color: #1e1e1e;
        color: #fff;
        text-align: left;
        border: 1px solid #444;
        border-radius: 8px;
        padding: 10px;
        position: absolute;
        z-index: 1000;
        bottom: 120%; /* Show above */
        left: 50%;
        margin-left: -125px;
        opacity: 0;
        transition: opacity 0.2s;
        box-shadow: 0px 4px 15px rgba(0,0,0,0.5);
        font-size: 12px;
        pointer-events: none; /* Let clicks pass through if needed, though mostly visual */
    }
    .ygo-tooltip img {
        width: 100%;
        border-radius: 4px;
        margin-bottom: 8px;
    }
    .ygo-tooltip h4 {
        margin: 0 0 5px 0;
        font-size: 14px;
        color: #ffcc00;
    }
    .ygo-tooltip p {
        margin: 0 0 5px 0;
        line-height: 1.3;
    }
    .ygo-badge {
        position: absolute;
        bottom: 0;
        right: 0;
        background-color: #000;
        color: #00ffcc;
        font-weight: bold;
        font-size: 11px;
        padding: 2px 4px;
        border-radius: 4px 0 4px 0;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Init Session State
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Display History
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"], unsafe_allow_html=True)

    # Chat Input
    if meta_query := st.chat_input("Fai una domanda sul Meta (es. Trend, Decklist, Counter)..."):
        
        # 1. User Message
        st.session_state.chat_history.append({"role": "user", "content": meta_query})
        with st.chat_message("user"):
            st.markdown(meta_query)
            
        # 2. Check Context
        if not st.session_state.meta_context:
            err_msg = "⚠️ **Database Vuoto!** Clicca 'Aggiorna Database Meta' in alto per scaricare i dati dei tornei."
            st.session_state.chat_history.append({"role": "assistant", "content": err_msg})
            with st.chat_message("assistant"):
                st.error(err_msg)
        else:
            # 3. AI Generation
            with st.chat_message("assistant"):
                placeholder = st.empty()
                placeholder.markdown("⏳ *Analisi strategica in corso...*")
                
                meta_model, _ = resolve_working_model()
                
                # Construct History Text for Prompt
                history_text = ""
                for msg in st.session_state.chat_history[-6:]: # Utili ultimi 3 turni (User+AI)
                    role_label = "UTENTE" if msg["role"] == "user" else "AI"
                    history_text += f"{role_label}: {msg['content']}\n"

                prompt_rag = f"""
                Sei un esperto di Yu-Gi-Oh! TCG.
                
                FONTE DI VERITÀ (DATI TORNEI):
                {st.session_state.meta_context}
                
                CRONOLOGIA CHAT RECENTE:
                {history_text}
                
                DOMANDA CORRENTE UTENTE: "{meta_query}"
                
                ISTRUZIONI COMPORTAMENTALI:
                1. **INTENTO & VELOCITÀ**: Sii CONCISO.
                    - Rispondi basandoti SUI DATI e sulla CRONOLOGIA.
                    - Usa elenchi puntati.
                    - Genera HTML SOLO se richiesto.
                
                2. **FORMATTAZIONE DECKLIST (HTML)** (Solo se richiesta):
                   - Struttura: `<div class="ygo-card-wrapper"><img src="...">...</div>`.
                   - Usa `<details>` per chiudere i mazzi lunghi.
                   
                3. **REGOLE**:
                   - Ignora OCG.
                   - Se la domanda si riferisce a "ciò che abbiamo detto prima", usa la CRONOLOGIA.
                """
                
                # Stream Response
                full_response = ""
                # placeholder is already created above
                try:
                    stream = meta_model.generate_content(prompt_rag, stream=True)
                    for chunk in stream:
                        if chunk.text:
                            full_response += chunk.text
                            placeholder.markdown(full_response + "▌", unsafe_allow_html=True)
                    placeholder.markdown(full_response, unsafe_allow_html=True)
                    
                    # Add to history
                    st.session_state.chat_history.append({"role": "assistant", "content": full_response})
                    
                except Exception as e:
                    st.error(f"Errore generazione: {e}")
