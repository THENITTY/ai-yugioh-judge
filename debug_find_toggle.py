
def find_toggle():
    with open("ym_tierlist_dump.html", "r") as f:
        content = f.read()
    
    # Search for "T3 Events Only"
    target = "T3 Events Only"
    idx = content.find(target)
    
    if idx == -1:
        print(f"Target '{target}' NOT FOUND in dump.")
    else:
        # Extract surrounding context
        start = max(0, idx - 400)
        end = min(len(content), idx + 400)
        snippet = content[start:end]
        print(f"--- SNIPPET AROUND '{target}' ---\n")
        print(snippet)
        print("\n------------------------------")

if __name__ == "__main__":
    find_toggle()
