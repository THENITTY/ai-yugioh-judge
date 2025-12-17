from playwright.sync_api import sync_playwright

def check_formats():
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
            
        anchors = page.query_selector_all("a[href*='/tournament/']")
        print(f"Found {len(anchors)} anchors.")
        
        for i, a in enumerate(anchors[:10]):
            href = a.get_attribute("href")
            # Get full row text
            row_text = a.evaluate("el => el.parentElement.parentElement.innerText").replace("\n", " | ")
            # Check for any specific format icons/tags? 
            # Often there is an image with title="Master Duel" etc.
            
            # Using evaluate to check for images in the row
            images_alts = a.evaluate("el => Array.from(el.parentElement.parentElement.querySelectorAll('img')).map(img => img.title || img.alt)")
            
            print(f"[{i}] {href}")
            print(f"    Text: {row_text}")
            print(f"    Imgs: {images_alts}")
            
        browser.close()

if __name__ == "__main__":
    check_formats()
