from playwright.sync_api import sync_playwright
import time

def dump_techs():
    url = "https://www.yugiohmeta.com/tier-list#techs"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print(f"Navigating to {url}...")
        page.goto(url, timeout=60000)
        
        # Click Techs Tab to be sure
        try:
            page.click("li:has-text('Techs')", force=True)
            print("Clicked Techs tab.")
            time.sleep(5) # Wait for content
        except Exception as e:
            print(f"Tab click warning: {e}")

        # Dump
        content = page.content()
        with open("ym_techs_dump.html", "w") as f:
            f.write(content)
        
        print("Dump saved to ym_techs_dump.html")
        browser.close()

if __name__ == "__main__":
    dump_techs()
