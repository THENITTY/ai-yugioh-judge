from yugioh_scraper import YuGiOhMetaScraper

def debug_scrape():
    scraper = YuGiOhMetaScraper()
    print("Starting YGOProDeck Scrape (Multi-Tier)...")
    links = scraper.get_ygoprodeck_tournaments(days_lookback=30)
    
    print(f"\n✅ Found {len(links)} tournaments.")
    for l in links[:5]:
        print(f" - {l}")
    if len(links) > 5: print(" ...")

if __name__ == "__main__":
    debug_scrape()
