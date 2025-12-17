from playwright.sync_api import sync_playwright
import os
import re

def debug_local():
    cwd = os.getcwd()
    # Ensure absolute path for file:// protocol
    url = f"file://{cwd}/ym_tierlist_dump.html"
    
    print(f"Loading local dump: {url}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        
        # 1. DEBUG DECK TYPES
        print("\n--- DECK TYPES ANALYSIS ---")
        containers = page.query_selector_all(".deck-type-container")
        print(f"Found {len(containers)} containers.")
        
        for i, c in enumerate(containers[:5]): # Check top 5
            name_el = c.query_selector(".label")
            name = name_el.inner_text().strip() if name_el else "Unknown"
            
            sub_el = c.query_selector(".bottom-sub-label")
            sub_text = sub_el.inner_text().strip() if sub_el else "NO SUB LABEL"
            
            print(f"#{i+1}: {name} | RAW SUB: '{sub_text}'")
            
            # DEBUG: Print full innerHTML for the first item to see structure
            if i == 0:
                print(f"\n--- INNER HTML FOR {name} ---\n")
                print(c.inner_html())
                print("\n------------------------------\n")
            
            # Test Regex
            count_match = re.search(r"\((\d+)\)", sub_text)
            percent_match = re.search(r"([\d\.]+)%", sub_text)
            print(f"   -> Match: Count={count_match.group(1) if count_match else 'None'} | %={percent_match.group(1) if percent_match else 'None'}")

        # 2. DEBUG TECHS TAB
        # Note: In the dump, we might NOT be able to click tabs if they require JS hydration/server calls!
        # The dump is a static snapshot. 
        # IF the tech tab was NOT active when dumped, we can't inspect it here.
        # But let's check if the button exists at least.
        print("\n--- TABS ANALYSIS ---")
        tech_tab = page.query_selector("li:has-text('Techs')")
        print(f"Tech Tab Found: {tech_tab is not None}")
        
        browser.close()

if __name__ == "__main__":
    debug_local()
