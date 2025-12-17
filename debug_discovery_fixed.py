from duckduckgo_search import DDGS

def test_fixed_logic():
    print("Testing FIXED Discovery Logic...")
    ddgs = DDGS()
    
    # Logic copied from app.py
    targets = ["YCS", "WCQ", "Regional", "National", "Championship"]
    urls_to_scrape = set()
    
    # 1. Broad Search
    search_queries = []
    for t in targets:
        search_queries.append(f"site:ygoprodeck.com/tournament/ {t}")

    print(f"Queries: {search_queries}")
    
    for kw in search_queries:
        try:
            print(f"Searching: {kw}")
            results = ddgs.text(kw, max_results=5)
            if results:
                for r in results:
                    link = r['href']
                    title = r['title']
                    snippet = r['body']
                    
                    # Relevance Check
                    if "2025" in title or "2025" in snippet or "December" in title or "November" in title:
                        print(f"✅ RELEVANT: {title} -> {link}")
                    else:
                        print(f"❌ SKIPPED (Old): {title}")
                        
        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    test_fixed_logic()
