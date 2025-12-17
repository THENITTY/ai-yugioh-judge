from yugioh_scraper import YuGiOhMetaScraper
import json

scraper = YuGiOhMetaScraper()
# Use the known working ID for Guadalajara
event_id = "6939f27648cc1f3f5896e744" 

print(f"Fetching decks for Event ID: {event_id}...")
decks = scraper.get_tournament_decks(event_id, limit=10)

print(f"\nFound {len(decks)} decks. Analyzing Placement Data:\n")

for i, d in enumerate(decks):
    placement = d.get("tournamentPlacement", "N/A")
    author = d.get("author", "Unknown")
    deck_type = d.get("deckType", {}).get("name", "Unknown")
    
    # Check for other potential rank fields
    swiss = d.get("swissPlacement", "N/A")
    top = d.get("topCut", "N/A") # Guessing field names
    
    print(f"#{i+1} | Player: {author} | Deck: {deck_type} | tournamentPlacement: {placement} (Type: {type(placement)})")
    # print(json.dumps(d, indent=2)) # Uncomment to see full JSON if needed
