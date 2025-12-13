# AI Yu-Gi-Oh! Judge ⚖️

Un assistente virtuale potenziato da Google Gemini per risolvere ruling di Yu-Gi-Oh! basandosi sui testi ufficiali delle carte.

## 🚀 Funzionalità
- **Riconoscimento Carte**: Scrivi la tua domanda, l'IA estrae i nomi delle carte (anche nickname).
- **Source of Truth**: Scarica i testi aggiornati dal database ufficiale YGOProDeck.
- **AI Ruling**: Un "Giudice Virtuale" analizza l'interazione tra le carte usando il regolamento ufficiale.
- **Retry Automatico**: Gestisce automaticamente i rate limit dell'API gratuita.

## 🛠 Installazione Locale

1. Clona il repository.
2. Crea un virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Installa le dipendenze:
   ```bash
   pip install -r requirements.txt
   ```
4. Avvia l'app:
   ```bash
   streamlit run app.py
   ```

## ☁️ Deployment

### Streamlit Cloud (Consigliato)
1. Pusha questo repo su GitHub.
2. Vai su [share.streamlit.io](https://share.streamlit.io).
3. Collega il repo.
4. Nelle impostazioni "Secrets", aggiungi:
   `GEMINI_API_KEY = "la-tua-chiave-qui"`

### Vercel
(Richiede configurazione aggiuntiva per Streamlit, si consiglia Streamlit Cloud per semplicità).
