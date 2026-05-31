import os
from google import genai

client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))

print("--- АКТУАЛЬНЫЕ МОДЕЛИ GOOGLE (API Source of Truth) ---")
models = client.models.list()
for m in models:
    # Фильтруем только те, что пригодны для генерации контента
    if 'generateContent' in getattr(m, 'supported_actions', []):
        print(f"ID: {m.name:30} | Version: {m.version}")
