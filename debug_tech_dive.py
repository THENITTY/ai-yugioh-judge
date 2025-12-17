from yugioh_scraper import YuGiOhMetaScraper
import json

def debug():
    print("Initializing Scraper...")
    scraper = YuGiOhMetaScraper()
    
    print("Running get_tech_deep_dive()...")
    data = scraper.get_tech_deep_dive()
    
    print("\n--- RESULTS ---")
    print(f"ALL Items: {len(data.get('all', []))}")
    print(f"T3 Items: {len(data.get('t3', []))}")
    
    if data['all']:
        print(f"Sample ALL: {data['all'][0]}")
    if data['t3']:
        print(f"Sample T3: {data['t3'][0]}")

if __name__ == "__main__":
    debug()
