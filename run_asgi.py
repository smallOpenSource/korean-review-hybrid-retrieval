import os
import sys
from asgiref.wsgi import WsgiToAsgi
from app import create_app

# Force Gemini first
os.environ['LLM_FALLBACK_ORDER'] = 'gemini,ollama,groq,openai'
os.environ['LOG_LEVEL'] = 'DEBUG'

flask_app = create_app()
asgi_app = WsgiToAsgi(flask_app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(asgi_app, host="0.0.0.0", port=5952)
