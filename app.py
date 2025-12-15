import os
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
                    for name, count in counts.most_common():
                        url = card_map.get(name, "")
                        # Salviamo nel contesto in formato: "3x Name <URL>" così l'LLM lo può parsare
                        card_lines.append(f"{count}x {name} <{url}>")
                    
                    deck_text.append(f"**{section_name}**:")
                    deck_text.append(", ".join(card_lines))
                    
        return "\n".join(deck_text) if deck_text else "Nessuna carta trovata."
    except Exception as e:
        return f"Errore scraping deck: {e}"

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
mode = st.sidebar.selectbox("Modalità di Utilizzo:", ["👨‍⚖️ AI Judge", "📊 Meta Analyst"])

# --- UI Principale ---
if mode == "👨‍⚖️ AI Judge":
    st.title("AI Yu-Gi-Oh! Judge ⚡️")
    st.markdown("### Il tuo assistente per i ruling complessi")

    # Inizializza modello standard per Judge
    model, active_model_name = resolve_working_model()
    st.sidebar.caption(f"🤖 Modello Judge: `{active_model_name}`")

    @st.cache_data
    def load_all_card_names():
        """Scarica e cach'a la lista di tutti i nomi delle carte (leggero)."""
        try:
            url = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()["data"]
                return [card["name"] for card in data]
            return []
        except Exception:
            return []

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
        st.rerun()

    # --- STEP 1: Input Domanda ---
    if st.session_state.step == 1:
        with st.expander("ℹ️ Come funziona?"):
            st.write("""
            1. Scrivi lo scenario OPPURE cerca direttamente le carte.
            2. Seleziona le carte coinvolte.
            3. Ricevi un verdetto rapido e tecnico.
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
                
                if total_cards > 0:
                    progress_bar.progress((idx + 1) / total_cards)
        with st.spinner("Generazione verdetto in corso..."):
            
            # USE STANDARD RESOLVED MODEL
            judge_model, model_name = resolve_working_model()

            # RULING UFFICIALI AGGIUNTIVE (YGOProDeck / Konami Database)
            # Inserito manualmente per gestire casi complessi come Mind Control vs Mirrorjade
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
    
            REGOLAMENTO CRITICO:
            - **Damage Step**: Sii ESTREMAMENTE severo. Solo carte che modificano direttamente ATK/DEF, Counter Traps, o effetti che negano specificamente *l'attivazione* (non l'effetto) possono essere attivate qui.
            - **Condizioni di Gioco (Game State)**: Verifica sempre se l'azione è permessa dallo stato attuale del gioco.
    
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
            
            response = get_gemini_response(model, prompt_ruling)
            
            if "---DETTAGLI---" in response:
                short_answer, deep_dive = response.split("---DETTAGLI---")
            else:
                short_answer = response
                deep_dive = "Nessun dettaglio tecnico aggiuntivo fornito."
    
            st.success(f"Verdetto Rapido (Model: {model_name}):")
            st.markdown(short_answer)
            
            with st.expander("🧐 Spiegazione Tecnica Approfondita"):
                st.markdown(deep_dive.strip())

            # --- EXPERIMENTAL: YGO RESOURCES SEARCH ---
            st.markdown("---")
            col_sc, col_new = st.columns([2, 1])
            with col_sc:
                if st.button("🔍 Consulta YGO Resources (OCG Rulings)"):
                    card_to_search = None
                    if 'found_cards' in locals() and found_cards:
                         card_to_search = found_cards[0]['name']
                    elif st.session_state.question_text:
                         card_to_search = st.session_state.question_text[:30] # Try with question snippet? risky
                    
                    if card_to_search:
                         with st.spinner(f"Cerco ruling OCG per '{card_to_search}' su db.ygoresources.com... (richiede ~10s)"):
                             try:
                                 scraper = YuGiOhMetaScraper()
                                 rulings_text = scraper.search_ygoresources_ruling(card_to_search)
                                 
                                 if rulings_text:
                                     st.info(f"📜 **Ruling OCG Trovati per '{card_to_search}':**")
                                     st.code(rulings_text, language="text")
                                     st.toast("Ruling trovati! Rileggili e valuta se cambia il verdetto.")
                                 else:
                                     st.warning(f"Nessun ruling specifico trovato per '{card_to_search}'.")
                             except Exception as e:
                                 st.error(f"Errore durante la ricerca: {e}")
                    else:
                         st.warning("Nessuna carta identificata per la ricerca.")

            with col_new:
                if st.button("Nuova Domanda 🔄"):
                    reset_judge()

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
        st.title(f"Meta Analyst: {meta_source} 📊")
        
        # ==========================================
        # MODALITÀ: YGOProDeck (Principale)
        # ==========================================
        if meta_source == "YGOProDeck (TCG)":
            st.markdown("### Analisi Trend, Top Cut e Decklist")
            
            if st.button("🔄 Aggiorna Database Meta (TCG)"):
                with st.spinner("Scansiono il Web (Tornei Recenti)..."):
                    try:
                        # CONFIGURAZIONE
                        HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
                        aggregated_text = f"DATA ANALISI: {datetime.now().strftime('%d %B %Y')}\nFONTE: YGOProDeck\n\n"
                        
                        urls_to_scrape = set()
                        scan_log = []
                        
                        # 1. Discovery Automatica (Playwright)
                        st.toast("🤖 Avvio Browser per cercare tornei recenti...")
                        scraper_tool = YuGiOhMetaScraper() # Utilizziamo la classe per accedere al metodo Playwright
                        
                        try:
                            # Usa il nuovo metodo Playwright (ultimi 60 giorni)
                            st.write("🗓️ Scansione ultimi 2 mesi (60 giorni)...")
                            found_links = scraper_tool.get_ygoprodeck_tournaments(days_lookback=60)
                            
                            if found_links:
                                st.success(f"✅ Trovati {len(found_links)} tornei nel periodo!")
                                for link in found_links:
                                    if link not in urls_to_scrape:
                                        urls_to_scrape.add(link)
                                        scan_log.append(f"🌍 Trovato: {link}")
                            else:
                                st.warning("⚠️ Nessun torneo trovato tramite Playwright. Provo fallback manuale...")
                        
                        except Exception as e:
                            st.error(f"Errore Playwright: {e}")

                        # 3. Deep Scrape dei Link Trovati
                        analyzed_count = 0
                        for url in urls_to_scrape:
                            try:
                                # Scarica HTML
                                resp = requests.get(url, headers=HEADERS, timeout=10)
                                soup = BeautifulSoup(resp.text, 'html.parser')
                                
                                # Estrai Titolo
                                page_title = soup.title.string if soup.title else url
                                
                                # Cerca Tabella Risultati (Struttura DIV o TABLE)
                                results_text = ""
                                rows_data = []
                                
                                # TENTATIVO 1: Struttura DIV (Nuova YGOProDeck)
                                div_table = soup.find('div', {'id': 'tournament_table'})
                                if div_table:
                                    # Itera sulle righe (che sono spesso link <a> o div)
                                    rows = div_table.find_all(['a', 'div'], class_='tournament_table_row')
                                    
                                    # 1. PRE-PROCESSAMENTO (Estrai metadati e Link)
                                    processed_items = [] # list of dict
                                    tasks = [] # (index, url)

                                    for i, row in enumerate(rows):
                                        cells = row.find_all('span', class_='as-tablecell')
                                        if len(cells) >= 3:
                                            place = cells[0].get_text(strip=True)
                                            
                                            # Player
                                            player_span = cells[1].find('span', class_='player-name')
                                            player = player_span.get_text(strip=True) if player_span else cells[1].get_text(strip=True)
                                            
                                            # Deck
                                            deck_cell = cells[2]
                                            deck_text = deck_cell.get_text(separator=" ", strip=True)
                                            variants = []
                                            for img in deck_cell.find_all('img', class_='archetype-tournament-img'):
                                                title = img.get('title')
                                                if title: variants.append(title)
                                            if variants: deck_text += " + " + " + ".join(variants)
                                            
                                            # Link
                                            deck_link = row.get('href') if row.name == 'a' else None
                                            if not deck_link:
                                                link_tag = deck_cell.find('a')
                                                if link_tag: deck_link = link_tag.get('href')
                                            
                                            # Top Cut Check
                                            is_top_cut = any(x in place.lower() for x in ["winner", "1st", "2nd", "top 4", "top 8"])
                                            
                                            item = {
                                                "place": place, "player": player, "deck_text": deck_text, "link": deck_link, "details": ""
                                            }
                                            
                                            if is_top_cut and deck_link and "deck/" in deck_link:
                                                tasks.append((i, deck_link))
                                            
                                            processed_items.append(item)

                                    # 2. ESECUZIONE PARALLELA (Fetch Deck Lists)
                                    if tasks:
                                        st.toast(f"📥 Scarico in parallelo {len(tasks)} liste per {page_title}...")
                                        with ThreadPoolExecutor(max_workers=10) as executor:
                                            future_to_idx = {executor.submit(scrape_deck_list, t[1]): t[0] for t in tasks}
                                            
                                            for future in as_completed(future_to_idx):
                                                idx = future_to_idx[future]
                                                try:
                                                    content = future.result()
                                                    if content:
                                                        processed_items[idx]["details"] = f"\n   [DETTAGLIO DECK]\n   {content.replace(chr(10), chr(10)+'   ')}\n"
                                                except Exception as exc:
                                                    pass

                                    # 3. GENERAZIONE REPORT
                                    for item in processed_items:
                                        rows_data.append(f"- {item['place']}: {item['player']} -> {item['deck_text']}{item['details']}")

                                if rows_data:
                                    results_text = "\n".join(rows_data)
                                    aggregated_text += f"\n=== REPORT: {page_title} ===\nURL: {url}\n{results_text}\n{'='*30}\n"
                                    analyzed_count += 1
                                    scan_log.append(f"✅ Letto: {page_title}")
                                
                            except Exception as e:
                                scan_log.append(f"❌ Errore {url}: {e}")

                        # 4. Salvataggio
                        st.session_state.meta_context = aggregated_text
                        st.session_state.meta_last_update = datetime.now().strftime("%H:%M")
                        
                        if analyzed_count > 0:
                            st.success(f"Analisi Completata! Importati {analyzed_count} report.")
                            with st.expander("Dettagli Scansione"):
                                for l in scan_log: st.write(l)
                        else:
                            st.error("Nessun dato utile estratto. Debug Info:")
                            st.code(scan_log)

                    except Exception as e:
                        st.error(f"Errore: {e}")

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
    st.markdown("### 💬 Chiedi al Giudice (Chat)")
    
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
                placeholder = st.empty()
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
