from yugioh_scraper import YuGiOhMetaScraper
import urllib.parse
import json

def test_url(url):
    print(f"\nTesting URL: {url}")
    scraper = YuGiOhMetaScraper()
    
    if "yugiohmeta.com" in url:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
    else:
        path = url
        
    if path.startswith("/top-decks"):
        path = path.replace("/top-decks", "", 1)
    
    if not path.startswith("/"):
        path = "/" + path

    # SIMULATE THE MISSING SLASH ISSUE
    # The API might require it.
    
    print(f"Final API Path: '{path}'")
    
    try:
        eid, name = scraper.get_event_id_from_deck_url(url)
        print(f"Result: ID={eid}, Name={name}")
    except Exception as e:
        print(f"Exception: {e}")

# Test WITHOUT trailing slash
test_url("https://www.yugiohmeta.com/top-decks/guadalajara-december-2025-regional/maliss/miguel-angel-hernandez-morales/SevyC")
