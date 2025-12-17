import requests
from bs4 import BeautifulSoup

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
url = "https://ygoprodeck.com/tournament/milan-wcq-regional-3907"

try:
    print(f"Fetching {url}...")
    resp = requests.get(url, headers=HEADERS, timeout=10)
    print(f"Status Code: {resp.status_code}")
    
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    div_table = soup.find('div', {'id': 'tournament_table'})
    if div_table:
        print("Found div#tournament_table")
        rows = div_table.find_all(['a', 'div'], class_='tournament_table_row')
        print(f"Found {len(rows)} rows")
        
        for i, row in enumerate(rows[:5]):
            cells = row.find_all('span', class_='as-tablecell')
            if len(cells) >= 3:
                place = cells[0].get_text(strip=True)
                deck_cell = cells[2]
                
                print(f"\n--- Row {i} Deck Cell HTML ---")
                print(deck_cell.prettify())
                
                deck_text = deck_cell.get_text(separator=" ", strip=True)
                
                # Check for images/icons with titles
                icons = deck_cell.find_all(['img', 'i'])
                for icon in icons:
                    print(f"Icon: {icon.name} | Title: {icon.get('title')} | Alt: {icon.get('alt')}")

                deck_link = row.get('href') if row.name == 'a' else None
                if not deck_link:
                    link_tag = deck_cell.find('a')
                    if link_tag:
                        deck_link = link_tag.get('href')
                
                print(f"Row {i}: {place} - {deck_text} - Link: {deck_link}")
                
    else:
        print("div#tournament_table NOT FOUND")
        # Check for fallback table
        tables = soup.find_all('table')
        print(f"Found {len(tables)} tables")

except Exception as e:
    print(f"EXCEPTION: {e}")
