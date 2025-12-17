from playwright.sync_api import sync_playwright
import time

def inspect_tierlist_retry():
    url = "https://www.yugiohmeta.com/tier-list"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print("Navigating...")
        page.goto(url, timeout=60000)
        
        try:
            # Wait for content to settle
            page.wait_for_load_state("networkidle")
            time.sleep(5) # Extra buffer for hydration
            
            # Dump HTML
            content = page.content()
            with open("ym_tierlist_dump.html", "w") as f:
                f.write(content)
            print("Dumped HTML to ym_tierlist_dump.html")
            
            # Print tabs text to verification
            # Looking for clickable tabs
            buttons = page.query_selector_all("button")
            print("\n--- BUTTONS FOUND ---")
            for b in buttons[:20]:
                print(f"Button: {b.inner_text()}")
                
        except Exception as e:
            print(f"Error: {e}")
            
        browser.close()

if __name__ == "__main__":
    inspect_tierlist_retry()
