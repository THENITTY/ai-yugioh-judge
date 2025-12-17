
def find_text():
    with open("ym_tierlist_dump.html", "r") as f:
        content = f.read()
    
    target = "20.44%"
    idx = content.find(target)
    
    if idx == -1:
        print(f"Target '{target}' NOT FOUND in dump.")
    else:
        start = max(0, idx - 200)
        end = min(len(content), idx + 200)
        snippet = content[start:end]
        print(f"--- SNIPPET AROUND {target} ---\n")
        print(snippet)
        print("\n------------------------------")

if __name__ == "__main__":
    find_text()
