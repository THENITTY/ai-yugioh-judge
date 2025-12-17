from playwright.sync_api import sync_playwright

def inspect_filters():
    url = "https://ygoprodeck.com/tournaments/"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        page.wait_for_selector("select", timeout=10000)
        
        selects = page.query_selector_all("select")
        print(f"Found {len(selects)} dropdowns.")
        
        for i, s in enumerate(selects):
            name = s.get_attribute("name")
            id_attr = s.get_attribute("id")
            print(f"\n--- Select #{i} (Name: {name}, ID: {id_attr}) ---")
            
            # Print first 10 options text and value
            options = s.query_selector_all("option")
            for j, o in enumerate(options[:15]):
                txt = o.inner_text()
                val = a_val = o.get_attribute("value")
                print(f"  [{j}] Text: '{txt}' -> Value: '{val}'")
                
        browser.close()

if __name__ == "__main__":
    inspect_filters()
