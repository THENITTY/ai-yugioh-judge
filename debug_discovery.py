from duckduckgo_search import DDGS
import datetime

def test_discovery():
    print("Testing DDGS Discovery...")
    ddgs = DDGS()
    
    current_month = datetime.datetime.now().strftime("%B %Y")
    
    # Queries to test
    queries = [
        f"site:ygoprodeck.com/tournament/ Regional {current_month}",
        f"site:ygoprodeck.com/tournament/ YCS {current_month}",
        f"site:ygoprodeck.com/tournament/ WCQ {current_month}",
        "ygoprodeck tournament results December 2025",
        "site:ygoprodeck.com/tournament/"
    ]
    
    print(f"Current Month: {current_month}")
    
    for q in queries:
        print(f"\n--- Query: {q} ---")
        try:
            results = ddgs.text(q, max_results=5)
            if results:
                for r in results:
                    print(f"FOUND: {r['title']} -> {r['href']}")
            else:
                print("NO RESULTS FOUND.")
        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    test_discovery()
