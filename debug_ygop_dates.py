from playwright.sync_api import sync_playwright

def check_dates():
    url = "https://ygoprodeck.com/tournaments/?type=Tier%202%20-%20Major%20Events"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print("Navigating...")
        page.goto(url, timeout=60000)
        
        try:
            page.wait_for_selector("a[href*='/tournament/']", timeout=20000)
        except:
            print("Timeout waiting for table.")
            
        # Get all rows or anchor containers
        # YGOProDeck usually puts the whole row as a clickable or has text nearby
        # Let's simple dump the text of the parent headers or divs
        
        # Strategy: Find the anchors, then look at their parent's text
        anchors = page.query_selector_all("a[href*='/tournament/']")
        print(f"Found {len(anchors)} anchors.")
        
        for i, a in enumerate(anchors[:5]):
            print(f"--- Item {i} ---")
            print(f"Href: {a.get_attribute('href')}")
            # print parent text
            parent = a.evaluate("el => el.parentElement.parentElement.innerText")
            print(f"Row Text: {parent.replace(chr(10), ' | ')}")
            
        browser.close()

if __name__ == "__main__":
    check_dates()
