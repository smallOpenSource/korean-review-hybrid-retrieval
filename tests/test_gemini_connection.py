import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('GEMINI_API_KEY')
print(f"API Key found: {bool(api_key)}")

if not api_key:
    print("Error: GEMINI_API_KEY not found in environment")
    exit(1)

try:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.0-flash')
    print("Attempting to generate content...")
    response = model.generate_content("Hello, are you working?")
    print(f"Response: {response.text}")
    print("Gemini connection successful!")
except Exception as e:
    print(f"Error connecting to Gemini: {e}")
