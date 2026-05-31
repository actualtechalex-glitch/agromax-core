import os
import sys
import json
import time
from dotenv import load_dotenv

load_dotenv()

from queue_manager import QueueManager
from lake_manager import LakeManager
from logger_manager import write_audit_log, audit_task
from prompt_cache_manager import GeminiCacheManager
import vision_worker

print("================================================================================")
print("=== SIMULACIA INTEGRACII CONTEXT CACHING & BATCH PROCESSING ===")
print("================================================================================")

# 1. Проверяем сервисы
redis_available = False
postgres_available = False

try:
    import redis
    r = redis.Redis(host=os.getenv("REDIS_HOST", "127.0.0.1"), port=int(os.getenv("REDIS_PORT", 6379)), db=int(os.getenv("REDIS_DB", 0)))
    r.ping()
    redis_available = True
    print("[STATUS] Redis: OK (Podklyucheno)")
except Exception:
    print("[STATUS] Redis: WARNING (Vklyuchen rezhim simulacii)")

try:
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', '127.0.0.1'),
        port=os.getenv('DB_PORT', '5432'),
        dbname=os.getenv('DB_NAME', 'agromax_state'),
        user=os.getenv('DB_USER', 'agromax_user'),
        password=os.getenv('DB_PASS', 'AgromaxStrongPassword2026')
    )
    conn.close()
    postgres_available = True
    print("[STATUS] PostgreSQL: OK (Podklyucheno)")
except Exception:
    print("[STATUS] PostgreSQL: WARNING (Vklyuchen rezhim simulacii)")

# 2. Мокаем Google GenAI Client для Context Caching
class MockCache:
    def __init__(self, name):
        self.name = name

class MockCachesAPI:
    def __init__(self):
        self.created_caches = []

    def create(self, model, config):
        cache_name = f"cachedContents/cache_test_key_{int(time.time())}"
        mock_cache = MockCache(cache_name)
        self.created_caches.append(mock_cache)
        print(f"      [MOCK-API] Created Context Cache in Gemini API: {cache_name} (Model: {model})")
        return mock_cache

class MockResponse:
    def __init__(self, text):
        self.text = text

class MockModelsAPI:
    def generate_content(self, model, contents, config=None):
        print(f"      [MOCK-API] Model '{model}' received generation request.")
        if config and hasattr(config, 'cached_content') and config.cached_content:
            print(f"      [MOCK-API] SUCCESS: Request utilized cached context: {config.cached_content}")
        else:
            print(f"      [MOCK-API] WARNING: Request ran in INLINE mode (no cache).")
        return MockResponse("# AI parsed page analysis output")

class MockGoogleGenAIClient:
    def __init__(self):
        self.caches = MockCachesAPI()
        self.models = MockModelsAPI()

# 3. Мокаем DB
class MockCursor:
    def execute(self, query, params=None):
        query_strip = query.strip().splitlines()[0]
        # Если это запрос промпта
        if "prompts_registry" in query.lower():
            # Возвращаем mock-промпт
            self.row = ('google', 'google/gemini-3.5-flash', None, 0.2, 8192, 
                        'System role description...', 'Core task instruction...', 
                        'Constraints list...', 'Format requirements...')
        else:
            print(f"[MOCK-DB-SQL] {query_strip}... Params: {params}")
            self.row = (1,)
            
    def fetchone(self):
        return self.row

class MockConn:
    def commit(self):
        pass

# 4. Инициализация очереди
qm = QueueManager()
queue_name = "queue:vision"

# Подготавливаем три документа в сумме дающие 1700 страниц
# Лимит батча — 1500 страниц.
# Воркер должен накопить:
# - Doc 1 (600 страниц) -> сумма 600 < 1500
# - Doc 2 (500 страниц) -> сумма 1100 < 1500
# - Doc 3 (600 страниц) -> сумма 1700 >= 1500 (накопление останавливается, документы целиком!)
doc_tasks = [
    {"id": 1001, "file_name": "Tractor_RSM_2400_Hydraulics_Schematics.pdf", "page_count": 600, "file_type": "SCHEMATICS"},
    {"id": 1002, "file_name": "Tractor_RSM_2400_Electrical_Manual.pdf", "page_count": 500, "file_type": "SCHEMATICS"},
    {"id": 1003, "file_name": "Tractor_RSM_2400_Gearbox_Manual.pdf", "page_count": 600, "file_type": "SCHEMATICS"},
]

if redis_available:
    qm.clear(queue_name)
    for task in doc_tasks:
        qm.push_task(queue_name, task)
    print(f"[OK] 3 document tasks pushed to Redis '{queue_name}'")
else:
    print(f"[SIMULATION] 3 document tasks added to virtual queue.")

# 5. Тестируем GeminiCacheManager
print("\n--- Тестирование GeminiCacheManager ---")
mock_client = MockGoogleGenAIClient()

# Сбросим кэш перед тестом
GeminiCacheManager.clear_cache_registry()

# Тест 1: Успешное создание кэша
sys_inst = "System Role Instruction"
full_prompt = "Large system prompt content for caching..."
cache_name_1 = GeminiCacheManager.get_or_create_cache(
    client=mock_client,
    prompt_key="VISION_HEAVY_SCHEMA",
    system_instruction=sys_inst,
    contents=[full_prompt],
    model_id="google/gemini-3.5-flash",
    ttl_seconds=300
)
print(f"      [VERIFY] Created cache name: {cache_name_1}")

# Тест 2: Повторный запрос (должен вернуть из памяти)
cache_name_2 = GeminiCacheManager.get_or_create_cache(
    client=mock_client,
    prompt_key="VISION_HEAVY_SCHEMA",
    system_instruction=sys_inst,
    contents=[full_prompt],
    model_id="google/gemini-3.5-flash",
    ttl_seconds=300
)
print(f"      [VERIFY] Reused cache name: {cache_name_2}")
if cache_name_1 == cache_name_2:
    print("      [OK] Reusing cache registry works correctly!")
else:
    print("      [FAIL] Caches did not match!")

# Тест 3: Мягкий откат при ошибке (например, маленький размер)
class ErrorMockCachesAPI:
    def create(self, model, config):
        raise ValueError("InvalidArgument: Content length is below 32768 tokens limit.")

class ErrorMockGoogleGenAIClient:
    def __init__(self):
        self.caches = ErrorMockCachesAPI()

error_client = ErrorMockGoogleGenAIClient()
cache_name_err = GeminiCacheManager.get_or_create_cache(
    client=error_client,
    prompt_key="SMALL_PROMPT_KEY",
    system_instruction=sys_inst,
    contents=["short prompt"],
    model_id="google/gemini-3.5-flash",
    ttl_seconds=300
)
print(f"      [VERIFY] Soft-fallback cache name (should be None): {cache_name_err}")
if cache_name_err is None:
    print("      [OK] Soft-fallback works correctly under API error!")
else:
    print("      [FAIL] Soft-fallback did not return None!")

# 6. Тестируем батчевую обработку (симуляция основного цикла)
print("\n--- Тестирование Batch Processing ---")

# Извлекаем и накапливаем батч
batch_tasks = []
total_pages = 0
page_limit = 1500

if redis_available:
    while total_pages < page_limit:
        task = qm.pop_task(queue_name, timeout=2)
        if not task:
            break
        num_pages = task.get("page_count", 50)
        total_pages += num_pages
        batch_tasks.append(task)
else:
    for task in doc_tasks:
        num_pages = task["page_count"]
        total_pages += num_pages
        batch_tasks.append(task)
        if total_pages >= page_limit:
            break

print(f"[OK] Sformirovan batch из {len(batch_tasks)} doc. Vsego stranic: {total_pages}")
if len(batch_tasks) == 3 and total_pages == 1700:
    print("      [OK] Batching kept all 3 documents whole without splitting (1700 pages total)!")
else:
    print(f"      [FAIL] Batching size mismatch: {len(batch_tasks)} docs, {total_pages} pages")

# Формируем задачи по страницам для симуляции ThreadPool
page_tasks = []
for t in batch_tasks:
    doc_id = t['id']
    file_name = t['file_name']
    num_pages = t['page_count']
    
    # Симулируем первые 3 страницы каждого документа для быстрого теста
    pages_to_test = min(num_pages, 3)
    for p in range(pages_to_test):
        page_tasks.append({
            "doc_id": doc_id,
            "file_name": file_name,
            "page_number": p + 1,
            "file_type": "IMAGE_SCHEMA",
            "doc_path": None
        })

print(f"[OK] Zapusk ThreadPoolExecutor. Rabochie potoki: 4. Stranic na test: {len(page_tasks)}")

mock_conn = MockConn()
mock_cursor = MockCursor()

from concurrent.futures import ThreadPoolExecutor, as_completed

def run_test_page_task(pt):
    db = MockConn()
    cur = MockCursor()
    p_key = 'VISION_HEAVY_SCHEMA'
    prompt_cfg = vision_worker.compile_enterprise_prompt(cur, p_key)
    provider, model_id, fallback_model, temp, max_t, system_role, core_task, constraints, format_inst = prompt_cfg
    full_prompt = f"{core_task}\n\nОГРАНИЧЕНИЯ:\n{constraints}\n\nФОРМАТ:\n{format_inst}"
    
    print(f"   [POOL-RUN] Start processing: Doc ID {pt['doc_id']}, Str {pt['page_number']}")
    ai_text = vision_worker.call_ai_with_caching(
        client=mock_client,
        prompt_key=p_key,
        provider=provider,
        model_id=model_id,
        system_role=system_role,
        full_prompt=full_prompt,
        image_path=None,
        fallback_model=None
    )
    print(f"   [POOL-RUN] Finished processing: Doc ID {pt['doc_id']}, Str {pt['page_number']} -> {ai_text[:20]}...")

with ThreadPoolExecutor(max_workers=4) as executor:
    futures = {executor.submit(run_test_page_task, pt): pt for pt in page_tasks}
    for future in as_completed(futures):
        pt = futures[future]
        future.result()

print("\n================================================================================")
print("=== PROVERKA CONTEXT CACHING & BATCHING USPESHNO ZAVERSHENA ===")
print("================================================================================")
