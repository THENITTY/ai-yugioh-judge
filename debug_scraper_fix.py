from yugioh_scraper import YuGiOhMetaScraper
import urllib.parse
import json

def test_url(url):
    print(f"\nTesting URL: {url}")
    scraper = YuGiOhMetaScraper()
    
    # Simulate the logic inside the class to debug it
    if "yugiohmeta.com" in url:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
    else:
        path = url
        
    print(f"Parsed Path: '{path}'")

    if path.startswith("/top-decks"):
        path = path.replace("/top-decks", "", 1)
    
    if not path.startswith("/"):
        path = "/" + path

    print(f"Final API Path: '{path}'")
    
    # Now actually call the method
    try:
        eid, name = scraper.get_event_id_from_deck_url(url)
        print(f"Result: ID={eid}, Name={name}")
        
        if eid:
            # Try fetching one deck to be sure
            decks = scraper.get_tournament_decks(eid, limit=1)
            print(f"Decks Found: {len(decks)}")
    except Exception as e:
        print(f"Exception: {e}")

# Test with the URL from the screenshot (reconstructed)
test_url("https://www.yugiohmeta.com/top-decks/guadalajara-december-2025-regional/maliss/miguel-angel-hernandez-morales/SevyC/")

# Test with just the path
test_url("/guadalajara-december-2025-regional/maliss/miguel-angel-hernandez-morales/SevyC/")
