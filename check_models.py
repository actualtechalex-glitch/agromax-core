import requests
import google.generativeai as genai
import os

# 1. Запрос к OpenRouter
print("--- OpenRouter Models (Caching-capable architectures) ---")
try:
    response = requests.get("https://openrouter.ai/api/v1/models")
    models = response.json().get('data', [])
    # Фильтруем те, что поддерживают кэш-архитектуры (claude 3.5+, gemini 2+)
    for m in models:
        if any(x in m['id'].lower() for x in ['claude-3-5', 'claude-3-6', 'gemini-2', 'gemini-3']):
            print(f"ID: {m['id']} | Provider: {m['provider_name']}")
except Exception as e:
    print(f"OpenRouter error: {e}")

# 2. Запрос к Google (через SDK)
print("\n--- Google Native Models (Supported Caching) ---")
try:
    # Требуется GOOGLE_API_KEY в окружении
    genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"Name: {m.name} | Display: {m.display_name}")
except Exception as e:
    print(f"Google SDK error (ensure GOOGLE_API_KEY is set): {e}")

# 3. Anthropic (Static List based on Cache-Architecture)
print("\n--- Anthropic Caching-Native Models (As of May 2026) ---")
print("claude-3-5-sonnet-20241022 (Claude 3.5 Sonnet)")
print("claude-3-6-sonnet-latest (Claude 3.6 Sonnet)")
print("claude-3-opus-20240229 (Claude 3 Opus)")
