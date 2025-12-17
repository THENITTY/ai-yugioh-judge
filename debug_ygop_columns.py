from playwright.sync_api import sync_playwright
import time

url = "https://ygoprodeck.com/tournaments/"

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
    )
    page = browser.new_page()
    print("Navigating...")
    page.goto(url, timeout=60000)
    
    try:
        page.wait_for_selector("#tournaments-table", timeout=15000)
        
        # Get Headers
        headers = page.evaluate("""() => {
            const ths = Array.from(document.querySelectorAll('#tournaments-table thead th'));
            return ths.map(th => th.innerText.trim());
        }""")
        print("Headers:", headers)
        
        # Get First Row
        first_row = page.evaluate("""() => {
            const tr = document.querySelector('#tournaments-table tbody tr');
            if(!tr) return [];
            const tds = Array.from(tr.querySelectorAll('td'));
            return tds.map(td => td.innerText.replace('\\n', ' ').trim());
        }""")
        print("First Row:", first_row)
        
    except Exception as e:
        print("Error:", e)
        
    browser.close()
