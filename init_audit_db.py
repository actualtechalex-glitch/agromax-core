import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": os.getenv("DB_PORT", "5432"),
    "database": os.getenv("DB_NAME", "agromax_state"),
    "user": os.getenv("DB_USER", "agromax_user"),
    "password": os.getenv("DB_PASS", "AgromaxStrongPassword2026")
}

def init_audit_table():
    ddl_query = """
    CREATE TABLE IF NOT EXISTS public.task_audit_log (
        log_id BIGSERIAL PRIMARY KEY,
        task_id VARCHAR(128) NOT NULL,
        worker_name VARCHAR(64),
        status VARCHAR(32), 
        payload_snippet JSONB,
        error_message TEXT,
        execution_time_ms INTEGER,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_audit_task_id ON public.task_audit_log (task_id);
    CREATE INDEX IF NOT EXISTS idx_audit_created_at ON public.task_audit_log (created_at DESC);
    """
    
    print("[INFO] Podklyucheniye k PostgreSQL dlya sozdaniya tablicy audita...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute(ddl_query)
        print("[INFO] Tablica public.task_audit_log i indeksy uspeshno sozdany!")
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"[ERROR] Oshibka sozdaniya tablicy audita: {e}")
        return False

if __name__ == '__main__':
    init_audit_table()
