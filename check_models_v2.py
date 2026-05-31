import os
from google import genai
from google.genai import types

# Инициализация клиента (требуется GOOGLE_API_KEY)
# Убедитесь, что ключ задан: export GOOGLE_API_KEY='...'
client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))

print("\n--- Google Native Models (Current & Cache-Capable) ---")
# Получаем список моделей
models = client.models.list()
for m in models:
    if 'generateContent' in m.supported_methods:
        print(f"ID: {m.name} | Display: {m.display_name}")

print("\n--- Note on Anthropic ---")
print("Claude 3.5 Sonnet (claude-3-5-sonnet-20241022) - Cache Ready")
print("Claude 3.6 Sonnet (claude-3-6-sonnet-latest) - Cache Ready")
