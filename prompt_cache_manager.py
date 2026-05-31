import os
import time

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

class GeminiCacheManager:
    """
    Менеджер кэширования контекста (Context Caching) для Google Gemini API.
    Предоставляет методы получения и создания кэша промптов с мягким откатом
    в случае ошибок API или малого объема данных (менее 32k токенов).
    """
    # Локальный реестр кэшей в памяти: prompt_key -> (cache_name, expire_time)
    _active_caches = {}

    @classmethod
    def get_or_create_cache(cls, client, prompt_key, system_instruction, contents, model_id, ttl_seconds=300):
        """
        Пытается вернуть имя существующего активного кэша контекста для prompt_key.
        Если кэш отсутствует или истек, пытается создать его через Google GenAI API.
        При возникновении ошибок (например, промпт меньше 32768 токенов) перехватывает
        их и возвращает None, перенаправляя выполнение на обычный inline-запрос.
        """
        now = time.time()
        
        # 1. Проверяем кэш в памяти
        if prompt_key in cls._active_caches:
            cache_name, expire_time = cls._active_caches[prompt_key]
            if now < expire_time:
                print(f"   [CACHE] Vosproizvodstvo suschestvuyuschego kesha: '{cache_name}' dlya key: {prompt_key}")
                return cache_name
            else:
                print(f"   [CACHE] Srok zhizni kesha dlya key '{prompt_key}' istek.")
                cls._active_caches.pop(prompt_key, None)
                
        # 2. Проверяем доступность SDK и клиента
        if genai is None or client is None:
            print("   [WARN] Google GenAI SDK ne podklyuchen. Keshirivanie otklucheno.")
            return None
            
        model_name = model_id.replace('google/', '')
        
        try:
            print(f"   [CACHE] Popitka sozdaniya kesha dlya '{prompt_key}' (Model: {model_name})...")
            
            if isinstance(contents, str):
                contents = [contents]
                
            config = types.CreateCachedContentConfig(
                contents=contents,
                system_instruction=system_instruction,
                display_name=f"cache_{prompt_key.lower()}",
                ttl=f"{ttl_seconds}s"
            )
            
            cache = client.caches.create(
                model=model_name,
                config=config
            )
            
            # Запоминаем имя кэша и время окончания с запасом в 10 секунд
            expire_time = now + ttl_seconds - 10
            cls._active_caches[prompt_key] = (cache.name, expire_time)
            print(f"   [OK] Kesh konteksta uspeshno sozdan: {cache.name} (TTL: {ttl_seconds}s)")
            return cache.name
            
        except Exception as e:
            # Мягкий откат при любых ошибках создания кэша
            print(f"   [WARN] Ne udalos sozdat kesh dlya '{prompt_key}': {e}. Perekhod v inline-rezhim.")
            return None

    @classmethod
    def clear_cache_registry(cls):
        """Очищает локальный реестр кэшей."""
        cls._active_caches.clear()
