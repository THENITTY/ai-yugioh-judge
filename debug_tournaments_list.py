from yugioh_scraper import YuGiOhMetaScraper
import json

scraper = YuGiOhMetaScraper()

def check_endpoint(name, params):
    print(f"\n--- Testing {name} ---")
    try:
        data = scraper._get_json(params)
        print(f"Items found: {len(data)}")
        if data and isinstance(data, list):
            for i, item in enumerate(data[:3]):
                date = item.get("date", "No Date")
                title = item.get("title") or item.get("name") or "No Title"
                eid = item.get("_id")
                print(f"[{i}] {date} | {title} | ID: {eid}")
    except Exception as e:
        print(f"Error: {e}")

# Test 1: Standard Tournaments Endpoint
check_endpoint("Tournaments API", {"url": "/api/v1/tournaments", "limit": 5, "sort": "-date"})

# Test 2: Articles with formatting (often used for feeds)
# Note: The scraper base URL is fixed to top-decks, so I need to hack it or userequests directly
import requests
url_articles = "https://www.yugiohmeta.com/api/v1/articles"
headers = scraper.HEADERS

print("\n--- Testing Articles API (TCG Tournaments) ---")
try:
    resp = requests.get(url_articles, headers=headers, params={"limit": 5, "sort": "-date", "category": "tcg-tournament"}, timeout=10)
    data = resp.json()
    for i, item in enumerate(data[:3]):
        date = item.get("date", "No Date")
        title = item.get("title", "No Title")
        print(f"[{i}] {date} | {title}")
except Exception as e:
    print(f"Error: {e}")
