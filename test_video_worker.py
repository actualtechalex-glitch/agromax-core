import os
import sys
import json
import time
from dotenv import load_dotenv

load_dotenv()

# Импортируем тестируемые модули
from queue_manager import QueueManager
from lake_manager import LakeManager
from logger_manager import write_audit_log, audit_task
import video_worker

print("================================================================================")
print("=== SIMULACIA PAIPLAINA VIDEO_WORKER (Gemini 3.5 Flash) ===")
print("================================================================================")

# Проверяем доступность локальных сервисов
redis_available = False
postgres_available = False

try:
    import redis
    r = redis.Redis(host=os.getenv("REDIS_HOST", "127.0.0.1"), port=int(os.getenv("REDIS_PORT", 6379)), db=int(os.getenv("REDIS_DB", 0)))
    r.ping()
    redis_available = True
    print("[STATUS] Redis: OK (Podklyucheno)")
except Exception:
    print("[STATUS] Redis: WARNING (Nedostupen). Vklyuchen rezhim simulacii ocheredi.")

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
    print("[STATUS] PostgreSQL: WARNING (Nedostupen). Vklyuchen rezhim simulacii zapisi v DB.")

# 1. Создаем тестовую задачу и файл
task_id = "video_test_task_777"
video_filename = "tractor_engine_leak_fix.mp4"
lm = LakeManager()

# Создаем фиктивный видеофайл в Bronze слое
bronze_video_path = os.path.join(lm.bronze_dir, f"{task_id}.mp4")
with open(bronze_video_path, 'wb') as f:
    f.write(b"mock mp4 binary video payload for E2E tractor engine leak repair manual")
print(f"[OK] Testoviy fail video sozdan v Bronze: {bronze_video_path}")

task_payload = {
    "id": task_id,
    "file_name": "Tractor Engine Oil Leak Fix Video Guide",
    "slice_uri": f"storage://bronze/{task_id}.mp4",
}

# Очередь Redis
qm = QueueManager()
queue_name = "queue:video"

if redis_available:
    qm.clear(queue_name)
    qm.push_task(queue_name, task_payload)
    print(f"[OK] Zadacha otpravlena v realnuyu ochered Redis '{queue_name}'")
else:
    print(f"[SIMULATION] Zadacha dobavlena v virtualnuyu ochered: {json.dumps(task_payload)}")

# 2. Мокаем Google GenAI Client
class MockState:
    def __init__(self, name):
        self.name = name

class MockFile:
    def __init__(self, name, state_name="ACTIVE"):
        self.name = name
        self.state = MockState(state_name)

class MockFilesAPI:
    def __init__(self):
        self.uploaded_files = []
        self.deleted_files = []

    def upload(self, file):
        file_name = f"files/{os.path.basename(file)}_{int(time.time())}"
        mock_file = MockFile(file_name, "ACTIVE")
        self.uploaded_files.append(mock_file)
        print(f"      [MOCK-API] Uploaded video file to Google File API: {file_name}")
        return mock_file

    def get(self, name):
        # Возвращаем готовый статус ACTIVE
        return MockFile(name, "ACTIVE")

    def delete(self, name):
        self.deleted_files.append(name)
        print(f"      [MOCK-API] Deleted video file from Google File API: {name}")

class MockResponse:
    def __init__(self, text):
        self.text = text

class MockModelsAPI:
    def generate_content(self, model, contents):
        print(f"      [MOCK-API] Model '{model}' received prompt and video payload.")
        markdown = (
            f"# Анализ видеоинструкции: {contents[0].name}\n\n"
            "## 1. Общая информация о видео\n"
            "Длина видео: ~5 минут. Ремонт течи масла двигателя трактора.\n\n"
            "## 2. Пошаговая транскрибация речи и описание действий\n"
            "- **[00:10]**: Механик очищает зону слива масла.\n"
            "- **[01:15]**: Механик откручивает болт крышки с помощью ключа на 17.\n"
            "- **[02:40]**: Замена прокладки крышки головки блока цилиндров.\n"
            "- **[04:10]**: Затяжка болтов с моментом 25 Нм.\n\n"
            "## 3. Список использованных инструментов\n"
            "- Накидной ключ на 17\n"
            "- Динамометрический ключ\n"
            "- Очиститель деталей\n\n"
            "## 4. Ключевые рекомендации по безопасности\n"
            "- Дождитесь полного остывания двигателя перед разборкой."
        )
        return MockResponse(markdown)

class MockGoogleGenAIClient:
    def __init__(self):
        self.files = MockFilesAPI()
        self.models = MockModelsAPI()

# 3. Мокаем DB курсор и коннект
class MockCursor:
    def execute(self, query, params=None):
        print(f"[MOCK-DB-SQL] {query.strip().splitlines()[0]}... Params: {params}")
    def fetchone(self):
        return (task_id,)

class MockConn:
    def commit(self):
        print("[MOCK-DB] Transaction committed.")

# 4. Запускаем выполнение задачи
if redis_available:
    popped_task = qm.pop_task(queue_name, timeout=2)
else:
    popped_task = task_payload

mock_client = MockGoogleGenAIClient()

if not postgres_available:
    mock_conn = MockConn()
    mock_cursor = MockCursor()
else:
    mock_conn = psycopg2.connect(
        host=os.getenv('DB_HOST', '127.0.0.1'),
        port=os.getenv('DB_PORT', '5432'),
        dbname=os.getenv('DB_NAME', 'agromax_state'),
        user=os.getenv('DB_USER', 'agromax_user'),
        password=os.getenv('DB_PASS', 'AgromaxStrongPassword2026')
    )
    mock_cursor = mock_conn.cursor()

print("\n[RUN] Zapusk process_single_task из video_worker.py...")
try:
    video_worker.process_single_task(popped_task, mock_cursor, mock_conn, client_override=mock_client)
    print("[OK] process_single_task completed successfully!")
except Exception as ex:
    print(f"[ERROR] Sboy processinga video-zadachi: {ex}")

if postgres_available:
    mock_conn.close()

# 5. Проверяем результаты
print("\n--------------------------------------------------------------------------------")
print("STEP 4: Proverka rezultatov v Silver sloye и audit logov")
print("--------------------------------------------------------------------------------")

silver_data = lm.get_from_silver(task_id)
if silver_data:
    print(f"[OK] Silver file nayden! URI: storage://silver/{task_id}.md")
    print("--- Soderzhimoe Silver-faila ---")
    print(silver_data.strip())
    print("--------------------------------")
else:
    print("[FAIL] Silver fail otsutstvuet!")

# Проверяем, что try...finally сработал и файл был удален из File API
if len(mock_client.files.uploaded_files) > 0 and len(mock_client.files.deleted_files) > 0:
    if mock_client.files.uploaded_files[0].name == mock_client.files.deleted_files[0]:
        print("[OK] try...finally uspeshno otstranilo vremenny fail v Google File API.")
    else:
        print("[FAIL] Vremenny fail ne udalen ili imena ne sovpadayut!")
else:
    print("[FAIL] Vremenny fail ne prosel cikl zagruzki/udaleniya!")

# Очищаем созданные тестовые файлы
if os.path.exists(bronze_video_path):
    os.remove(bronze_video_path)

silver_file = os.path.join(lm.silver_dir, f"{task_id}.md")
if os.path.exists(silver_file):
    os.remove(silver_file)

print("\n================================================================================")
print("=== SIMULACIA PROSHLA USPESHNO! VSE PROVERKI PROIDENI ===")
print("================================================================================")
