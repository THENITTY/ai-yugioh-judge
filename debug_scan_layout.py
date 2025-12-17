from playwright.sync_api import sync_playwright
import time

def scan_layout():
    url = "https://www.yugiohmeta.com/tier-list#techs"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=60000)
        
        try:
            page.click("li:has-text('Techs')", force=True)
            time.sleep(3)
        except:
            pass

        # Find the first row
        first_row = page.query_selector("div.columns.is-align-items-center.is-mobile")
        if first_row:
            # Get parent
            parent = first_row.evaluate_handle("el => el.parentElement")
            print("\n--- PARENT INNER HTML (Truncated) ---")
            html = parent.evaluate("el => el.innerHTML")
            print(html[:2000])
            
            # Count children
            count = parent.evaluate("el => el.children.length")
            print(f"\nParent has {count} children.")
            
            # Print class of child #4
            print("\n--- CHILD #4 HTML ---")
            child4 = parent.evaluate(f"el => el.children[3] ? el.children[3].outerHTML : 'NO CHILD 4'")
            print(child4)

        browser.close()

if __name__ == "__main__":
    scan_layout()
