import requests
import urllib.parse
import streamlit as st

class YuGiOhMetaScraper:
    BASE_URL = "https://www.yugiohmeta.com/api/v1/top-decks"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.yugiohmeta.com/"
    }

    def __init__(self):
        pass

    def _get_json(self, params):
        try:
            response = requests.get(self.BASE_URL, headers=self.HEADERS, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching data: {e}")
            return []

    def get_event_id_from_deck_url(self, deck_url):
        """
        Fetches a single deck to extract its Event ID.
        deck_url can be a full URL or a path like /tier-list/deck-types/...
        """
        # Extract path from URL if needed
        if "yugiohmeta.com" in deck_url:
            parsed = urllib.parse.urlparse(deck_url)
            path = parsed.path
        else:
            path = deck_url

        # Clean path: remove /top-decks prefix if present (common in browser URL)
        if path.startswith("/top-decks"):
            path = path.replace("/top-decks", "", 1)
        
        # Ensure it starts with /
        if not path.startswith("/"):
            path = "/" + path

        # Ensure it ends with / (API requirement)
        if not path.endswith("/"):
            path = path + "/"

        # The API expects the 'url' param to be the path
        data = self._get_json({"url": path, "limit": 1})
        
        if data and isinstance(data, list) and len(data) > 0:
            deck_data = data[0]
            if "event" in deck_data and "_id" in deck_data["event"]:
                return deck_data["event"]["_id"], deck_data["event"].get("name", "Unknown Tournament")
        
        return None, None

    def get_tournament_decks(self, event_id, limit=50):
        """
        Fetches all decks for a given Event ID.
        """
        params = {
            "event": event_id,
            "limit": limit,
            "sort": "-created" # Ensure consistent ordering
        }
        return self._get_json(params)

    def analyze_coverage(self, decks):
        """
        Analyzes the list of decks to determine missing top cut data.
        Returns a summary string.
        """
        counts = {}
        for d in decks:
            p = d.get("tournamentPlacement", -1)
            # Use float for consistency
            try:
                p = float(p)
            except:
                pass
            counts[p] = counts.get(p, 0) + 1
            
        # Expected counts (Generic Logic)
        # 1.0 -> Winner (1)
        # 2.0 -> Finalist (1)
        # 3.5 -> Top 4 (2)
        # 8.0 -> Top 8 (4)
        # 16.0 -> Top 16 (8)
        
        missing = []
        
        # Check Winner
        if counts.get(1.0, 0) < 1: missing.append("Winner")
        
        # Check Finalist
        if counts.get(2.0, 0) < 1: missing.append("Finalist")
        
        # Check Top 4 (Rank 3.5 or 3/4)
        has_top4 = counts.get(3.5, 0) + counts.get(3, 0) + counts.get(4, 0)
        if has_top4 < 2: missing.append(f"Top 4 ({2 - has_top4} missing)")
        
        # Check Top 8 (Rank 8 or 5-8)
        # Often Rank 8 means "Top 8", so there should be 4 of them.
        has_top8 = counts.get(8.0, 0) + sum(counts.get(i, 0) for i in range(5, 9))
        if has_top8 < 4: missing.append(f"Top 8 ({4 - has_top8} missing)")
        
        if not missing:
            return "✅ Full Top Cut Data Available"
            
        return "⚠️ Missing Data: " + ", ".join(missing)

    def get_links_from_roundup(self, roundup_url):
        """
        Uses Playwright to render the page and extract all deck links.
        Returns a list of absolute URLs.
        """
        from playwright.sync_api import sync_playwright
        import time
        
        links = set()
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
                )
                page = browser.new_page()
                page.goto(roundup_url, timeout=30000)
                
                # Wait for initial load
                try:
                    page.wait_for_selector("a[href*='/top-decks/']", timeout=10000)
                except:
                    print("Timeout waiting for deck links.")

                # SCROLL LOOP for Lazy Loading
                # Scroll down repeatedly to trigger new items
                previous_count = 0
                for _ in range(5): # Try scrolling 5 times
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(2) # Wait for network/animation
                    
                    # Check current count
                    current_count = len(page.query_selector_all("a[href*='/top-decks/']"))
                    if current_count == previous_count and current_count > 0:
                        # No new items loaded after scroll
                        break
                    previous_count = current_count
                    
                # Extract all matching anchors
                anchors = page.query_selector_all("a[href*='/top-decks/']")
                
                for a in anchors:
                    href = a.get_attribute("href")
                    if href:
                        # Normalize to full URL
                        if href.startswith("/"):
                            href = "https://www.yugiohmeta.com" + href
                        links.add(href)
                        
                browser.close()
                
            return list(links)
        except Exception as e:
            print(f"Playwright Error: {e}")
            return []

            print(f"Playwright Error: {e}")
            return []

            print(f"Playwright Error: {e}")
            return []

    def get_ygoprodeck_tournaments(self, days_lookback=60):
        """
        Uses Playwright to scrape YGOProDeck Tournaments page.
        Filters by date (default last 60 days).
        Returns list of full tournament URLs.
        """
        from playwright.sync_api import sync_playwright
        import time
        from datetime import datetime, timedelta
        import re
        
        links = []
        url = "https://ygoprodeck.com/tournaments/?type=Tier%202%20-%20Major%20Events"
        threshold_date = datetime.now() - timedelta(days=days_lookback)
        
        print(f"DEBUG: Searching tournaments strictly after {threshold_date.strftime('%Y-%m-%d')}")
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
                )
                page = browser.new_page()
                page.goto("https://ygoprodeck.com/tournaments/", timeout=60000)
                
                # Loop through desired tiers
                # User requested Tier 2 and Tier 3. 
                # value: Label
                TARGET_TIERS = {"2": "Competitive", "3": "Premier"}
                
                seen = set() # Initialize seen set here to accumulate across tiers
                regex_date = re.compile(r"([A-Z][a-z]{2} \d{1,2}, \d{4})") # Dec 14, 2025
                
                # STRICT OCG & FORMAT FILTER
                BLACKLIST_KEYWORDS = [
                    "Master Duel", "Speed Duel", "Duel Links", "Rush Duel", "Time Wizard", "Edison", "Goat",
                    "Japan", "Korea", "China", "Philippines", "Thailand", "Singapore", "Malaysia", "Taiwan", "Vietnam"
                ]
                
                MIN_PLAYERS = 80

                for tier_val, tier_label in TARGET_TIERS.items():
                    print(f"DEBUG: Scraping Tier '{tier_label}' (Value: {tier_val})...")
                    try:
                        # 1. Wait for Dropdowns (ensure existing)
                        page.wait_for_selector("#filter-tier", state="attached", timeout=15000)
                        
                        # 2. Apply Tier via JS (Bypasses visibility)
                        page.evaluate(f"document.getElementById('filter-tier').value = '{tier_val}';")
                        page.evaluate("document.getElementById('filter-tier').dispatchEvent(new Event('change'));")
                        time.sleep(2) # Wait for reload
                        
                        # 3. Apply "TCG" via JS
                        page.evaluate("document.getElementById('filter-format').value = 'TCG';")
                        page.evaluate("document.getElementById('filter-format').dispatchEvent(new Event('change'));")
                        time.sleep(1) 
                        
                        # 4. Set "Show 100 entries"
                        # This might be a standard select or custom. 
                        # Let's try standard select based on previous code working intermittently, but JS is safer if we can find ID.
                        # The limit selector doesn't have an obvious ID in previous context, but likely 'name="tournaments-table_length"' or similar.
                        # We stick to the 'find select with option 100' loop but use JS to set it if found.
                        selects = page.query_selector_all("select")
                        for s in selects:
                            try:
                                # Check if it has 100 option
                                has_100 = s.evaluate("el => !!el.querySelector('option[value=\"100\"]')")
                                if has_100:
                                    s.evaluate("el => { el.value = '100'; el.dispatchEvent(new Event('change')); }")
                                    break
                            except: pass
                        time.sleep(3) # Wait for table reload
                        
                        # SCROLL LOOP
                        for _ in range(5):
                            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            time.sleep(1)
                        
                        # Extract anchors for this tier
                        current_anchors = page.query_selector_all("a[href*='/tournament/']")
                        
                        for a in current_anchors:
                            href = a.get_attribute("href")
                            if not href or "/tournament/" not in href or href in seen:
                                continue
                            
                            # Validates Text & Player Count
                            row_data = a.evaluate("""
                                el => {
                                    const tr = el.closest('tr');
                                    if (!tr) return { text: el.innerText, players: 0 };
                                    const cells = tr.querySelectorAll('td');
                                    // Column 3 (0-indexed) is # Players
                                    const playerText = cells[3] ? cells[3].innerText : "0";
                                    return { 
                                        text: tr.innerText, 
                                        players: playerText 
                                    };
                                }
                            """)
                            
                            row_text = row_data["text"]
                            player_raw = row_data["players"]
                            
                            # Blacklist Check
                            if any(bad_word.lower() in row_text.lower() for bad_word in BLACKLIST_KEYWORDS):
                                continue

                            # Player Count Check
                            try:
                                clean_players = re.sub(r"[^\d]", "", player_raw)
                                players_count = int(clean_players) if clean_players else 0
                                if players_count < MIN_PLAYERS:
                                    continue
                            except:
                                if "Unknown" not in player_raw: continue

                            # Date Check
                            match = regex_date.search(row_text)
                            if match:
                                date_str = match.group(1)
                                try:
                                    # Parse "Dec 14, 2025"
                                    # Note: YGOProDeck format is "Dec 14, 2025"
                                    row_date = datetime.strptime(date_str, "%b %d, %Y")
                                    if row_date >= threshold_date:
                                        # Normalize URL
                                        if href.startswith("/"):
                                            href = "https://ygoprodeck.com" + href
                                        links.append(href)
                                        seen.add(href)
                                except: pass
                                
                    except Exception as e:
                        print(f"Error scraping Tier {tier_label}: {e}")
                        continue # Try next tier

                browser.close()
            
            return list(links)
        except Exception as e:
            print(f"Playwright Error YGOP: {e}")
            return []

    def _format_rank(self, placement):
        try:
            val = float(placement)
            if val == 1: return "🥇 Winner"
            if val == 2: return "🥈 Finalist"
            if val <= 4: return "Top 4"
            if val <= 8: return "Top 8"
            if val <= 16: return "Top 16"
            if val <= 32: return "Top 32"
            if val <= 64: return "Top 64"
            return f"Rank {val}"
        except:
            return str(placement)

    def get_tier_list_data(self):
        """
        Scrapes yugiohmeta.com/tier-list for:
        1. Deck Breakdown (Name, %, Count)
        2. Top Techs (Main Deck Staples)
        3. Side Deck Staples
        Returns a dict.
        """
        from playwright.sync_api import sync_playwright
        import time
        import re
        
        url = "https://www.yugiohmeta.com/tier-list"
        data = {
            "decks": [],
            "techs": [],
            "side": []
        }
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
                )
                page = browser.new_page()
                page.goto(url, timeout=60000)
                
                # 1. Scrape DECK TYPES (Default View)
                try:
                    page.wait_for_selector(".deck-type-container", timeout=15000)
                    containers = page.query_selector_all(".deck-type-container")
                    
                    for c in containers:
                        try:
                            # 1. Get Name
                            name_el = c.query_selector(".label")
                            name = name_el.inner_text().strip() if name_el else "Unknown"
                            
                            # 2. Get Stats
                            # Strategy: Try inner label first (Tier 2/3), then sibling H3 (Tier 1)
                            sub_text = ""
                            sub_el = c.query_selector(".bottom-sub-label")
                            
                            if sub_el:
                                sub_text = sub_el.inner_text().strip()
                            else:
                                # Check for Sibling H3 (Tier 1 Layout)
                                # Evaluate JS to peek at next sibling
                                sibling_text = c.evaluate("el => el.nextElementSibling?.tagName === 'H3' ? el.nextElementSibling.innerText : ''")
                                if sibling_text:
                                    sub_text = sibling_text.strip()
                            
                            # 3. Parse Stats
                            # Format: "(75) 20.44%"
                            if not sub_text:
                                continue # Skip if no stats found (e.g. ad or ghost element)

                            count_match = re.search(r"\((\d+)\)", sub_text)
                            percent_match = re.search(r"([\d\.]+)%", sub_text)
                            
                            count = count_match.group(1) if count_match else "0"
                            percent = percent_match.group(1) if percent_match else "0"
                            
                            data["decks"].append({
                                "name": name,
                                "count": count,
                                "percent": percent
                            })
                        except Exception as loop_e:
                            # print(f"Skipping a deck: {loop_e}")
                            continue

                except Exception as e:
                    print(f"Error scraping Decks: {e}")

                # Helper to scrape cards from a tab
                def scrape_cards():
                    cards = []
                    try:
                        # Wait for cards to appear. 
                        # YugiohMeta cards usually have class 'img-button' OR 'card-container'
                        # We wait for at least one to be visible to ensure tab loaded
                        page.wait_for_selector("a.img-button", timeout=5000)
                    except:
                        pass # proceed anyway, maybe list is empty

                    items = page.query_selector_all("a.img-button")
                    for it in items[:30]: # Limit to top 30
                        try:
                            lbl = it.query_selector(".label")
                            if not lbl: continue
                            c_name = lbl.inner_text().strip()
                            
                            # Usage often in .bottom-sub-label e.g. "3x (100%)" or similar
                            sub = it.query_selector(".bottom-sub-label")
                            c_usage = sub.inner_text().strip() if sub else ""
                            
                            cards.append({"name": c_name, "usage": c_usage})
                        except:
                            continue
                    return cards

                # 2. Scrape TECHS
                try:
                    # Click Tab "Techs"
                    # Use force=True to ensure click filters through potential overlaps
                    page.click("li:has-text('Techs')", force=True) 
                    time.sleep(2) # Animation buffer
                    data["techs"] = scrape_cards()
                except Exception as e:
                    print(f"Error scraping Techs: {e}")

                # 3. Scrape SIDE-DECK
                try:
                    page.click("li:has-text('Side-Deck')", force=True)
                    time.sleep(2)
                    data["side"] = scrape_cards()
                except Exception as e:
                    print(f"Error scraping Side: {e}")
                    
                browser.close()
                
            return data
            
        except Exception as e:
            print(f"Playwright Error TierList: {e}")
            return data

    def get_tech_deep_dive(self):
        """
        Specific scraper for the 'Techs' tab.
        Captures two datasets:
        1. ALL Events (Standard)
        2. T3 Events Only (High Competitive)
        Returns a dict with 'all' and 't3' lists.
        """
        from playwright.sync_api import sync_playwright
        import time
        import re
        
        url = "https://www.yugiohmeta.com/tier-list#techs"
        data = {"all": [], "t3": []}
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
                )
                page = browser.new_page()
                page.goto(url, timeout=60000)
                
                # Helper to scrape visible cards
                def scrape_current_view():
                    cards = []
                    
                    # 1. Force Scroll
                    try:
                        for _ in range(5): 
                            page.keyboard.press("PageDown")
                            time.sleep(1)
                        # Wait for at least the top rows
                        page.wait_for_selector("div.columns.is-align-items-center.is-mobile", timeout=10000)
                    except:
                        pass # proceed to standard scrape
                        
                    # 2. STRATEGY A: Top Rows (List View)
                    # Contains: <a>Name</a> ... <h3>Stats</h3>
                    rows = page.query_selector_all("div.columns.is-align-items-center.is-mobile")
                    for row in rows:
                        try:
                            # Verify if this is a card row (has link and h3)
                            link = row.query_selector("a[href^='/cards/']")
                            if not link: continue
                            
                            lbl = link.query_selector(".label")
                            c_name = lbl.inner_text().strip() if lbl else "Unknown"
                            
                            h3 = row.query_selector("h3")
                            c_stats = h3.inner_text().strip() if h3 else ""
                            
                            match = re.search(r"\((\d+)\)\s*([\d\.]+%)\s*\|\s*([\d\.]+)", c_stats)
                            if match:
                                cards.append({
                                    "name": c_name,
                                    "count": match.group(1),
                                    "percent": match.group(2),
                                    "avg": match.group(3)
                                })
                        except: continue

                    # 3. STRATEGY B: Grid Items (Grid View)
                    # Contains: <a class='column'> ... <div class='bottom-sub-label'>Stats</div> </a>
                    # We target the anchor directly which acts as the container in the grid
                    grid_items = page.query_selector_all("div.columns.is-multiline a.column")
                    for item in grid_items:
                        try:
                            lbl = item.query_selector(".label")
                            if not lbl: continue
                            c_name = lbl.inner_text().strip()
                            
                            # Stats in bottom-sub-label
                            sub = item.query_selector(".bottom-sub-label")
                            c_stats = sub.inner_text().strip() if sub else ""
                            
                            match = re.search(r"\((\d+)\)\s*([\d\.]+%)\s*\|\s*([\d\.]+)", c_stats)
                            if match:
                                cards.append({
                                    "name": c_name,
                                    "count": match.group(1),
                                    "percent": match.group(2),
                                    "avg": match.group(3)
                                })
                        except: continue
                        
                    # Dedup by name (keeping first occurrence which is usually higher rank)
                    seen = set()
                    unique_cards = []
                    for c in cards:
                        if c["name"] not in seen:
                            seen.add(c["name"])
                            unique_cards.append(c)
                            
                    return unique_cards[:40] # Return top 40 unique

                # 1. Click Techs Tab (Safety)
                try:
                    page.click("li:has-text('Techs')", force=True)
                    time.sleep(3)
                except:
                    pass

                # 2. Scrape ALL Events
                print("Scraping ALL Events...")
                data["all"] = scrape_current_view()
                
                # 3. Toggle T3 Events Only
                print("Toggling T3 Events...")
                # The label text is "T3 Events Only". 
                # The switch container is previous sibling of the span.
                # Simplest way: Find the text, get parent, find input/label.
                # Or click the text itself if label wraps? No, text is separate span.
                # Let's find the span and click the checkbox in previous sibling.
                
                # JS Click might be safest
                page.evaluate("""
                    () => {
                        const spans = Array.from(document.querySelectorAll('span'));
                        const t3Span = spans.find(s => s.innerText.includes('T3 Events Only'));
                        if (t3Span) {
                            // The layout is: div.switch-container > label > input
                            // The span is sibling to div.switch-container in parent div.col
                            const parent = t3Span.parentElement;
                            const switchInput = parent.querySelector('input[type="checkbox"]');
                            if (switchInput) switchInput.click();
                        }
                    }
                """)
                time.sleep(4) # Wait for reload
                
                # 4. Scrape T3 Events
                print("Scraping T3 Events...")
                data["t3"] = scrape_current_view()
                
                browser.close()
                return data

        except Exception as e:
            print(f"Tech Deep Dive Error: {e}")
            return data

    def parse_deck_list(self, deck_data):
        """
        Converts raw deck JSON into a standardized string format for the AI.
        """
        output = []
        
        try:
            player = deck_data.get("author", "Unknown Player")
            deck_name = deck_data.get("deckType", {}).get("name", "Unknown Deck")
            raw_rank = deck_data.get("tournamentPlacement", "N/A")
            rank_str = self._format_rank(raw_rank)
            
            # Build Card List (sorted by amount)
            main_deck = []
            raw_main = deck_data.get("main", [])
            # Sort: desc by amount, then asc by name
            raw_main.sort(key=lambda x: (-x.get("amount", 0), x.get("card", {}).get("name", "")))
            
            for card in raw_main:
                name = card.get("card", {}).get("name", "Unknown Card")
                count = card.get("amount", 1)
                main_deck.append(f"{count}x {name}")
                
            output.append(f"- {rank_str}: {player} ({deck_name})")
            output.append(f"  Main Deck: {', '.join(main_deck)}")
            
            return "\n".join(output)
        except Exception as e:
            return f"Error parsing deck: {e}"

# Usage Example (for integration)
# scraper = YuGiOhMetaScraper()
# eid, name = scraper.get_event_id_from_deck_url("/guadalajara-december-2025-regional/maliss/...")
# if eid:
#     decks = scraper.get_tournament_decks(eid)
#     for d in decks:
#         print(scraper.parse_deck_list(d))
