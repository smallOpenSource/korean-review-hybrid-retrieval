import os
import sys

# Force Gemini first
os.environ['LLM_FALLBACK_ORDER'] = 'gemini,ollama,groq,openai'
os.environ['LOG_LEVEL'] = 'DEBUG'

from app import create_app

# Force debug logging
os.environ['FLASK_ENV'] = 'development'

app = create_app()

if __name__ == "__main__":
    print("Starting Flask app manually...")
    app.run(host='0.0.0.0', port=5952, debug=False, use_reloader=False)
