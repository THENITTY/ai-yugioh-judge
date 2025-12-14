import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    # Try to read from keys.json if env not set
    import json
    try:
        with open("keys.json") as f:
            data = json.load(f)
            # Pick first available key
            api_key = list(data.values())[0]
    except:
        print("No API Key found")
        exit()

genai.configure(api_key=api_key)

print("Listing available models...")
for m in genai.list_models():
    if "generateContent" in m.supported_generation_methods:
        print(f"- {m.name}")

print("\nTesting Tool Support with 'gemini-1.5-flash':")
try:
    model = genai.GenerativeModel('gemini-1.5-flash', tools='google_search_retrieval')
    print("Success: gemini-1.5-flash initialized with tools.")
except Exception as e:
    print(f"Failed: {e}")

print("\nTesting Tool Support with 'models/gemini-1.5-flash-latest':")
try:
    model = genai.GenerativeModel('models/gemini-1.5-flash-latest', tools='google_search_retrieval')
    print("Success: models/gemini-1.5-flash-latest initialized with tools.")
except Exception as e:
    print(f"Failed: {e}")

print("\nTesting Tool Support with 'gemini-1.5-pro':")
try:
    model = genai.GenerativeModel('gemini-1.5-pro', tools='google_search_retrieval')
    print("Success: gemini-1.5-pro initialized with tools.")
except Exception as e:
    print(f"Failed: {e}")
