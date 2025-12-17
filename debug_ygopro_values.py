from playwright.sync_api import sync_playwright

def check_values():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://ygoprodeck.com/tournaments/", timeout=60000)
        
        page.wait_for_selector("#filter-tier", state="attached")
        
        # Get values and text
        options = page.eval_on_selector_all("#filter-tier option", 
            "opts => opts.map(o => ({val: o.value, text: o.innerText}))")
        print("TIER OPTIONS:", options)
        
        # Check Format
        page.wait_for_selector("#filter-format", state="attached")
        f_options = page.eval_on_selector_all("#filter-format option", 
            "opts => opts.map(o => ({val: o.value, text: o.innerText}))")
        print("FORMAT OPTIONS:", f_options)
        
        browser.close()

if __name__ == "__main__":
    check_values()
