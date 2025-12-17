from playwright.sync_api import sync_playwright

def check_filters():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://ygoprodeck.com/tournaments/", timeout=60000)
        
        page.wait_for_selector("#filter-tier", state="attached")
        
        # Get all options even if hidden
        options = page.eval_on_selector_all("#filter-tier option", "opts => opts.map(o => o.innerText)")
        print("TIER OPTIONS:", options)
        
        browser.close()

if __name__ == "__main__":
    check_filters()
