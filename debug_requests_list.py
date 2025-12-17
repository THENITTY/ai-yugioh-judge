import requests
from bs4 import BeautifulSoup

url = "https://ygoprodeck.com/tournaments/?type=Tier%202%20-%20Major%20Events"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

try:
    resp = requests.get(url, headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # Check for tournament links
    links = []
    for a in soup.find_all('a', href=True):
        if "/tournament/" in a['href']:
            links.append(a['href'])
            
    print(f"Found {len(links)} tournament links.")
    for l in links[:5]:
        print(f" - {l}")

except Exception as e:
    print(f"Error: {e}")
