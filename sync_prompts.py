import os, sys, csv, json
import requests
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# ID вашей таблицы, который мы достали из ссылки
SPREADSHEET_ID = "1_WBnA7SOLDOEZ_4KdyMqpf9y4AfGpM3Fjgi-sisyu4U"

def get_db():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        dbname=os.getenv('DB_NAME', 'agromax_state'),
        user=os.getenv('DB_USER', 'agromax_user'),
        password=os.getenv('DB_PASS', 'AgromaxStrongPassword2026')
    )

def fetch_sheet_csv(sheet_name):
    # Качаем лист таблицы как чистый CSV файл по прямой ссылке
    url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
    resp = requests.get(url)
    if resp.status_code != 200:
        raise Exception(f"Не удалось прочитать лист {sheet_name}. Статус: {resp.status_code}")
    
    lines = resp.text.splitlines()
    reader = csv.reader(lines)
    return list(reader)

def main():
    print("="*80)
    print("🔄 СТАРТ СИНХРОНИЗАЦИИ ПРОМПТОВ ЧЕРЕЗ ПУБЛИЧНЫЙ КАНАЛ (CSV) 🔄")
    print("="*80)
    
    db = get_db()
    
    try:
        print("📥 Скачивание матриц из Google Sheets...")
        registry_rows = fetch_sheet_csv("Registry")
        roles_rows = fetch_sheet_csv("Roles")
        
        # Отрезаем первую строчку с заголовками колонок
        if len(registry_rows) > 0: registry_rows = registry_rows[1:]
        if len(roles_rows) > 0: roles_rows = roles_rows[1:]

        with db:
            with db.cursor() as cur:
                # Очищаем старые таблицы в Postgres
                cur.execute("TRUNCATE TABLE public.prompts_registry CASCADE;")
                print("🧹 Локальные таблицы промптов в Postgres зачищены.")
                
                prompt_ids = {}
                for row in registry_rows:
                    if not row or len(row) < 4: continue
                    key, provider, model, fallback = row[0], row[1], row[2], row[3]
                    if not key: continue # Пропуск пустых строк
                    
                    temp = float(row[4]) if len(row) > 4 and row[4] else 0.0
                    tokens = int(row[5]) if len(row) > 5 and row[5] else 8192
                    status = row[6] if len(row) > 6 and row[6] else 'ACTIVE'
                    desc = row[7] if len(row) > 7 else ''
                    
                    cur.execute("""
                        INSERT INTO public.prompts_registry (prompt_key, provider, model_id, fallback_model_id, temperature, max_tokens, status, description)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
                    """, (key, provider, model, fallback, temp, tokens, status, desc))
                    
                    prompt_ids[key] = cur.fetchone()[0]
                    print(f"⚙️  Настройка [{key}] импортирована. Провайдер: {provider} | Модель: {model}")
                
                print("-" * 50)
                for row in roles_rows:
                    if not row or len(row) < 5: continue
                    key, role, task, constraints, format_inst = row[0], row[1], row[2], row[3], row[4]
                    if not key: continue
                    
                    if key in prompt_ids:
                        cur.execute("""
                            INSERT INTO public.prompt_roles (prompt_id, system_role, core_task, strict_constraints, output_format_instructions)
                            VALUES (%s, %s, %s, %s, %s);
                        """, (prompt_ids[key], role, task, constraints, format_inst))
                        print(f"📝 Системная инструкция для [{key}] успешно уложена.")
                        
        print("="*80)
        print("🎉 СИНХРОНИЗАЦИЯ УСПЕШНО ЗАВЕРШЕНА! Матрица ИИ обновлена.")
        print("="*80)
        
    except Exception as e:
        print(f"❌ КРИТИЧЕСКИЙ СБОЙ СИНХРОНИЗАЦИИ: {e}")

if __name__ == '__main__':
    main()
