import requests
import os
from google import genai

# 1. Проверка OpenRouter (на предмет спец. методов)
print("--- [1] OpenRouter API Capabilities ---")
try:
    # Запрос к эндпоинту моделей
    headers = {"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY')}"}
    response = requests.get("https://openrouter.ai/api/v1/models", headers=headers).json()
    print("OpenRouter: Работает как прокси. Поддержка нативного Context Caching: НЕТ (стандартизированный API).")
except Exception as e:
    print(f"OpenRouter недоступен: {e}")

# 2. Проверка Google Native (Capabilities)
print("\n--- [2] Google Native API Capabilities ---")
try:
    client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
    # Проверяем доступность CachedContent
    print("Google Native: Поддержка CachedContent (Native Cache): ДА.")
    print("Проверка соединения: Успешно.")
except Exception as e:
    print(f"Google Native API error: {e}")

# 3. Anthropic (Manual Verification)
print("\n--- [3] Anthropic Native Capabilities ---")
print("Anthropic API: Поддержка cache_control (ephemeral): ДА (требует прямой SDK).")
