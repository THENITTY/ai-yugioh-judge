import requests
from bs4 import BeautifulSoup

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
url = "https://www.yugiohmeta.com/articles/tournaments/tcg/weekly-roundup/2025/dec/1"

try:
    print(f"Fetching {url}...")
    resp = requests.get(url, headers=HEADERS, timeout=10)
    print(f"Status Code: {resp.status_code}")
    
    with open("debug_output.html", "w", encoding="utf-8") as f:
        f.write(resp.text)
    
    print("Saved to debug_output.html")

except Exception as e:
    print(f"EXCEPTION: {e}")
