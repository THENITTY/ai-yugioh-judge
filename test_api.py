import requests

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
# Hypothesized API URL based on MasterDuelMeta structure
url = "https://www.yugiohmeta.com/api/v1/articles/tournaments/tcg/weekly-roundup/2025/dec/1"
url_v2 = "https://www.yugiohmeta.com/api/articles/tournaments/tcg/weekly-roundup/2025/dec/1" 

try:
    print(f"Testing API 1: {url}...")
    resp = requests.get(url, headers=HEADERS, timeout=10)
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        print("SUCCESS! JSON Content:")
        print(resp.text[:500])
        
    print(f"\nTesting API 2: {url_v2}...")
    resp2 = requests.get(url_v2, headers=HEADERS, timeout=10)
    print(f"Status: {resp2.status_code}")

except Exception as e:
    print(f"EXCEPTION: {e}")
