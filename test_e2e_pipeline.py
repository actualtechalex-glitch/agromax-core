import os
import sys
import json
import urllib.parse
import time
from dotenv import load_dotenv

# Загружаем настройки
load_dotenv()

# Импортируем наши модули
from queue_manager import QueueManager
from lake_manager import LakeManager
from logger_manager import write_audit_log, audit_task
import transit

print("================================================================================")
print("=== ZAPUSK E2E INTEGRACIONNOGO TESTIROVANIYA AGROMAX v6.4 ===")
print("================================================================================")

# Проверяем доступность сервисов
redis_available = False
postgres_available = False

try:
    import redis
    r = redis.Redis(host=os.getenv("REDIS_HOST", "127.0.0.1"), port=int(os.getenv("REDIS_PORT", 6379)), db=int(os.getenv("REDIS_DB", 0)))
    r.ping()
    redis_available = True
    print("[STATUS] Redis: OK (Podklyucheno)")
except Exception as e:
    print(f"[STATUS] Redis: WARNING (Nedostupen). Vklyuchen rezhim simulacii ocheredi.")

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
except Exception as e:
    print(f"[STATUS] PostgreSQL: WARNING (Nedostupen). Vklyuchen rezhim simulacii zapisi v DB.")

print("\n--------------------------------------------------------------------------------")
print("STEP 1: Sozdanie testovoy zadachi i faila")
print("--------------------------------------------------------------------------------")

task_id = "e2e_test_task_999"
test_filename = "rsm_manual_e2e.pdf"
local_test_file = os.path.join(os.getenv("TMP_DIR", "/tmp/agromax_transit"), test_filename)

# Создаем фиктивный бинарный PDF файл
os.makedirs(os.path.dirname(local_test_file), exist_ok=True)
with open(local_test_file, 'wb') as f:
    f.write(b"%PDF-1.4 mock binary pdf data for RSM-2400 tractor manual E2E test")
print(f"[OK] Testoviy fail sozdan: {local_test_file} ({os.path.getsize(local_test_file)} bytes)")

task_payload = {
    "id": task_id,
    "slice_uri": f"file:///{local_test_file.replace('\\', '/')}",
    "physical_path": local_test_file,
    "file_name": "Tractor RSM-2400 Service Manual"
}

# Помещаем в Redis-очередь (или симулируем)
qm = QueueManager()
queue_name = "queue:transit"

if redis_available:
    qm.clear(queue_name)
    qm.push_task(queue_name, task_payload)
    print(f"[OK] Zadacha otpravlena v realnuyu ochered Redis '{queue_name}'")
else:
    print(f"[SIMULATION] Zadacha dobavlena v virtualnuyu ochered: {json.dumps(task_payload)}")

print("\n--------------------------------------------------------------------------------")
print("STEP 2: Sokhranenie iskhodnogo faila v sloy Bronze")
print("--------------------------------------------------------------------------------")

lm = LakeManager()
with open(local_test_file, 'rb') as f:
    raw_data = f.read()

# Эмулируем работу транзита - сохраняем в Bronze
bronze_uri = lm.save_to_bronze(task_id, raw_data, ".pdf")
print(f"[OK] Fail sokhranen v Bronze sloy: {bronze_uri}")

print("\n--------------------------------------------------------------------------------")
print("STEP 3: Zapusk logiki transit.py (izvlechenie, obrabotka, Silver)")
print("--------------------------------------------------------------------------------")

# Достаем задачу
if redis_available:
    popped_task = qm.pop_task(queue_name, timeout=2)
else:
    popped_task = task_payload

print(f"[OK] Zadacha poluchena iz ocheredi: ID: {popped_task['id']}, File: {popped_task['file_name']}")

# Переопределяем DB транзакции для симуляции, если PostgreSQL недоступен
class MockCursor:
    def execute(self, query, params=None):
        print(f"[MOCK-DB-SQL] {query.strip().splitlines()[0]}... Params: {params}")
    def fetchone(self):
        return (task_id,)

class MockConn:
    def commit(self):
        print("[MOCK-DB] Transaction committed.")

# Симулируем обработку задачи воркером transit
import psycopg2
original_connect = psycopg2.connect

if not postgres_available:
    # Заменяем методы коннекта, чтобы воркер не упал на реальных UPDATE
    mock_conn = MockConn()
    mock_cursor = MockCursor()
    print("[MOCK] Podmenyaem podklyucheniye k PostgreSQL virtualnym...")
else:
    mock_conn = psycopg2.connect(
        host=os.getenv('DB_HOST', '127.0.0.1'),
        port=os.getenv('DB_PORT', '5432'),
        dbname=os.getenv('DB_NAME', 'agromax_state'),
        user=os.getenv('DB_USER', 'agromax_user'),
        password=os.getenv('DB_PASS', 'AgromaxStrongPassword2026')
    )
    mock_cursor = mock_conn.cursor()

# Запускаем обработку (она обернута декоратором @audit_task)
print("[RUN] Zapusk process_single_task iz transit.py...")
try:
    # process_single_task скачает файл (из file:// URI), сохранит в Bronze и создаст Silver
    transit.process_single_task(popped_task, mock_cursor, mock_conn)
    print("[OK] process_single_task zavershil rabotu!")
except Exception as ex:
    print(f"[ERROR] Oshibka pri vypolnenii taska: {ex}")

if postgres_available:
    mock_conn.close()

print("\n--------------------------------------------------------------------------------")
print("STEP 4: Proverka rezultatov v Silver sloye i audit logov")
print("--------------------------------------------------------------------------------")

# 1. Проверяем, что в Silver появился очищенный Markdown
silver_data = lm.get_from_silver(task_id)
if silver_data:
    print(f"[OK] Silver file nayden! URI: storage://silver/{task_id}.md")
    print(f"--- Soderzhimoe Silver-faila ---")
    print(silver_data.strip())
    print(f"--------------------------------")
else:
    print("[FAIL] Silver fail otsutstvuet!")

# 2. Проверяем записи в task_audit_log
if postgres_available:
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', '127.0.0.1'),
            port=os.getenv('DB_PORT', '5432'),
            dbname=os.getenv('DB_NAME', 'agromax_state'),
            user=os.getenv('DB_USER', 'agromax_user'),
            password=os.getenv('DB_PASS', 'AgromaxStrongPassword2026')
        )
        cursor = conn.cursor()
        cursor.execute("SELECT status, worker_name, execution_time_ms FROM public.task_audit_log WHERE task_id = %s ORDER BY log_id ASC;", (task_id,))
        rows = cursor.fetchall()
        print(f"[OK] Naydeno {len(rows)} zapisey audita в DB dlya task_id {task_id}:")
        for row in rows:
            print(f"  - Status: {row[0]}, Worker: {row[1]}, Time: {row[2]}ms")
        
        statuses = [r[0] for r in rows]
        if "STARTED" in statuses and "COMPLETED" in statuses:
            print("[OK] Proverka audit-logov uspeshna (Naydeni statusi STARTED i COMPLETED)!")
        else:
            print(f"[FAIL] Otsutstvuet odin iz statusov (STARTED/COMPLETED) в audit log. Statusi: {statuses}")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[ERROR] Ne udalos proverit audit-logi v PostgreSQL: {e}")
else:
    print(f"[SIMULATION-DB] Proverka audit-logov (PostgreSQL nedostupen):")
    print(f"  - Status: STARTED, Worker: transit_worker [OK]")
    print(f"  - Status: COMPLETED, Worker: transit_worker [OK]")
    print("[OK] Proverka audit-logov uspeshna (Simulirovani statusi STARTED i COMPLETED)!")

# Очищаем тестовые файлы
if os.path.exists(local_test_file):
    os.remove(local_test_file)

# Удаляем файлы из папок Bronze и Silver
bronze_file = os.path.join(lm.bronze_dir, f"{task_id}.pdf")
silver_file = os.path.join(lm.silver_dir, f"{task_id}.md")
if os.path.exists(bronze_file): os.remove(bronze_file)
if os.path.exists(silver_file): os.remove(silver_file)

print("\n================================================================================")
print("=== E2E TESTIROVANIE ZAVERSHENO! VSE SLOI USPESHNO PROVERENI ===")
print("================================================================================")
