import os
import time
import glob
import urllib.parse
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

from queue_manager import QueueManager
from lake_manager import LakeManager
from logger_manager import audit_task

try:
    from google import genai
except ImportError:
    genai = None

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": os.getenv("DB_PORT", "5432"),
    "database": os.getenv("DB_NAME", "agromax_state"),
    "user": os.getenv("DB_USER", "agromax_user"),
    "password": os.getenv("DB_PASS", "AgromaxStrongPassword2026")
}

TMP_DIR = os.getenv("TMP_DIR", "/tmp/agromax_transit")
os.makedirs(TMP_DIR, exist_ok=True)

@audit_task(worker_name="video_worker")
def process_single_task(task, cursor, conn, client_override=None):
    """
    Обрабатывает одну задачу видеоанализа с использованием Gemini 3.5 Flash.
    """
    task_id = str(task['id'])
    file_name = task['file_name']
    
    lm = LakeManager()
    
    # 1. Поиск видеофайла в Bronze слое по task_id (без считывания всего файла в память)
    pattern = os.path.join(lm.bronze_dir, f"{task_id}.*")
    found_files = glob.glob(pattern)
    if not found_files:
        raise FileNotFoundError(f"Video file for Task ID {task_id} not found in Bronze layer ({lm.bronze_dir}).")
        
    local_video_path = found_files[0]
    
    # 2. Инициализация клиента Google GenAI
    if client_override:
        client = client_override
    else:
        if genai is None:
            raise ImportError("Google GenAI SDK is not installed ('google-genai' package is missing).")
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set.")
        client = genai.Client(api_key=api_key)
        
    print(f"   [INFO] Zashifrovka cherez Gemini: {file_name}")
    print(f"   [INFO] Zagruzka faila {local_video_path} v Google GenAI File API...")
    
    # Загружаем видеофайл в Google File API
    video_file = client.files.upload(file=local_video_path)
    print(f"   [OK] Faila zagruzhen. Imya v API: {video_file.name}")
    
    try:
        # Ожидание обработки видеофайла
        print("   [INFO] Ozhidanie processinga video na storone Google...")
        while True:
            # Получаем актуальный статус файла
            video_file = client.files.get(name=video_file.name)
            if video_file.state.name == "ACTIVE":
                print("   [OK] Video gotovo dlya analiza.")
                break
            elif video_file.state.name == "FAILED":
                raise RuntimeError("Google GenAI File API processing failed (FAILED state).")
            elif video_file.state.name == "PROCESSING":
                time.sleep(5)
            else:
                print(f"   [WARN] Neizvestny status: {video_file.state.name}, ozhidanie...")
                time.sleep(5)
                
        # 3. Запрос к модели gemini-3.5-flash
        prompt = (
            "Выполните синхронную транскрибацию речи на русском языке из данного видео, "
            "а также подробно опишите все визуальные действия механика по ремонту или обслуживанию техники. "
            "Результат должен быть структурирован в формате Markdown с временными метками (таймкодами).\n\n"
            "Разделы:\n"
            "1. Общая информация о видео\n"
            "2. Пошаговая транскрибация речи и описание действий с таймкодами (например, [00:15])\n"
            "3. Список использованных инструментов\n"
            "4. Ключевые рекомендации и предупреждения по безопасности"
        )
        
        print("   [INFO] Otpravka zaprosa k gemini-3.5-flash...")
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=[video_file, prompt]
        )
        markdown_result = response.text
        
        # 4. Сохранение Markdown-анализа в Silver слой
        silver_uri = lm.save_to_silver(task_id, markdown_result)
        print(f"   [OK] Rezultat video-analiza sokhranen v Silver: {silver_uri}")
        
        # 5. Запись статусов и ссылки в БД
        cursor.execute("""
            UPDATE public.slices_registry 
            SET ai_status = 'COMPLETED', storage_path = %s, file_type = 'VIDEO_ANALYSIS', timestamp_done = NOW() 
            WHERE id = %s;
        """, (silver_uri, task_id))
        conn.commit()
        print(f"   [OK] Status dlya Task ID {task_id} obnovlen v DB.")
        
    finally:
        # 6. Гарантированное удаление временного файла из Google File API cherez try...finally
        print(f"   [INFO] Udalenie vremennogo faila {video_file.name} iz Google File API...")
        try:
            client.files.delete(name=video_file.name)
            print("   [OK] Vremenny fail v Google File API uspeshno udalen.")
        except Exception as delete_err:
            print(f"   [WARN] Ne udalos udalit vremenny fail iz Google API: {delete_err}")

def process_pipeline():
    init_dir = os.path.dirname(os.path.abspath(__file__))
    print("=== Multimodal VIDEO_WORKER v1.0 (Gemini 3.5 Flash) ===")
    processed_count = 0
    qm = QueueManager()
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        while True:
            task = qm.pop_task("queue:video", timeout=5)
            
            if not task:
                print(f"\n[STATUS] Ochered pusta! Obrabotano video-zadach: {processed_count}")
                break
                
            print(f"\n[{processed_count+1}] V rabote video-zadacha ID: {task['id']}")
            try:
                process_single_task(task, cursor, conn)
            except Exception as e:
                print(f"   [ERROR] Oshibka processinga video-zadachi: {e}")
                
            processed_count += 1

        cursor.close(); conn.close()
    except Exception as e: 
        print(f"\n🚨 OSHIBKA: {e}")

if __name__ == "__main__":
    process_pipeline()
