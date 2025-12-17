
def find_tech_card():
    target = "Ash Blossom"
    file_path = "ym_techs_dump.html"
    
    try:
        with open(file_path, "r") as f:
            content = f.read()
        
        idx = content.find(target)
        if idx == -1:
            print(f"❌ '{target}' NOT FOUND in {file_path}")
            print("The dump might be empty or the Tab did not load.")
        else:
            print(f"✅ Found '{target}' at index {idx}")
            start = max(0, idx - 400)
            end = min(len(content), idx + 600)
            print("--- HTML CONTEXT ---")
            print(content[start:end])
            print("--------------------")
            
    except Exception as e:
        print(f"Error reading dump: {e}")

if __name__ == "__main__":
    find_tech_card()
