from playwright.sync_api import sync_playwright

def find_show_entries():
    url = "https://ygoprodeck.com/tournaments/"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        try:
            # Wait for any select
            page.wait_for_selector("select", timeout=15000)
            
            selects = page.query_selector_all("select")
            print(f"Found {len(selects)} dropdowns.")
            
            for i, s in enumerate(selects):
                # Check options values
                options = s.query_selector_all("option")
                values = [o.get_attribute("value") for o in options]
                texts = [o.inner_text() for o in options]
                
                print(f"Select #{i}: name='{s.get_attribute('name')}' class='{s.get_attribute('class')}'")
                print(f"  Values: {values}")
                
                if "100" in values and "50" in values:
                    print("  !!! FOUND SHOW ENTRIES !!!")
                    
        except Exception as e:
            print(f"Error: {e}")
            
        browser.close()

if __name__ == "__main__":
    find_show_entries()
