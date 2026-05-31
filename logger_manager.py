import os
import time
import json
import psycopg2
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": os.getenv("DB_PORT", "5432"),
    "database": os.getenv("DB_NAME", "agromax_state"),
    "user": os.getenv("DB_USER", "agromax_user"),
    "password": os.getenv("DB_PASS", "AgromaxStrongPassword2026")
}

def write_audit_log(task_id, worker_name, status, payload_snippet=None, error_message=None, execution_time_ms=None):
    """
    Записывает аудит выполнения задачи в таблицу public.task_audit_log.
    Обрабатывает сбои подключения к БД без прерывания основного процесса.
    """
    payload_json = None
    if payload_snippet:
        try:
            # Превращаем в плоский dict/json, убирая несериализуемые объекты
            clean_payload = {}
            for k, v in payload_snippet.items():
                if isinstance(v, (str, int, float, bool, type(None))):
                    clean_payload[k] = v
                else:
                    clean_payload[k] = str(v)
            payload_json = json.dumps(clean_payload)
        except Exception as e:
            payload_json = json.dumps({"serialization_error": str(e)})

    # Лог в стандартный вывод воркера
    print(f"[AUDIT] Worker: {worker_name} | Task ID: {task_id} | Status: {status} | Time: {execution_time_ms or 0}ms")
    if error_message:
         print(f"[AUDIT] Error: {error_message}")

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO public.task_audit_log 
            (task_id, worker_name, status, payload_snippet, error_message, execution_time_ms)
            VALUES (%s, %s, %s, %s, %s, %s);
        """, (task_id, worker_name, status, payload_json, error_message, execution_time_ms))
        cursor.close()
        conn.close()
    except Exception as e:
        # Логируем сбой СУБД, но не бросаем ошибку дальше, чтобы не сломать воркер
        print(f"[WARN] logger_manager: Ne udalos zapisat log v DB: {e}")

def audit_task(worker_name):
    """
    Декоратор для автоматического логирования выполнения задач воркерами.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Ищем объект задачи (обычно первый аргумент)
            task = args[0] if args else kwargs.get('task')
            
            task_id = "UNKNOWN"
            payload = {}
            if isinstance(task, dict):
                task_id = str(task.get('id', 'UNKNOWN'))
                payload = task
            elif hasattr(task, 'id'):
                task_id = str(task.id)
                if hasattr(task, 'keys'):
                    payload = dict(task)
                elif hasattr(task, '__dict__'):
                    payload = {k: v for k, v in task.__dict__.items() if not k.startswith('_')}

            start_time = time.time()
            write_audit_log(
                task_id=task_id,
                worker_name=worker_name,
                status="STARTED",
                payload_snippet=payload
            )
            try:
                result = func(*args, **kwargs)
                execution_time = int((time.time() - start_time) * 1000)
                
                write_audit_log(
                    task_id=task_id,
                    worker_name=worker_name,
                    status="COMPLETED",
                    payload_snippet=payload,
                    execution_time_ms=execution_time
                )
                return result
            except Exception as e:
                import traceback
                execution_time = int((time.time() - start_time) * 1000)
                tb_msg = f"{str(e)}\n\nTraceback:\n{traceback.format_exc()}"
                write_audit_log(
                    task_id=task_id,
                    worker_name=worker_name,
                    status="FAILED",
                    payload_snippet=payload,
                    error_message=tb_msg,
                    execution_time_ms=execution_time
                )
                raise e
        return wrapper
    return decorator

if __name__ == '__main__':
    print("--- TEST LOGGER_MANAGER ---")
    @audit_task("test_worker")
    def mock_task_func(task, status="ok"):
        if status != "ok":
            raise ValueError("Task execution failed mock")
        time.sleep(0.1)
        return "result_success"

    try:
        mock_task_func({"id": 777, "file_name": "manual_rsm.pdf"})
        print("OK: Test 1 (Success) completed.")
        
        try:
            mock_task_func({"id": 888, "file_name": "error_rsm.pdf"}, status="fail")
        except ValueError:
            print("OK: Test 2 (Fail) caught correctly.")
    except Exception as e:
        print(f"FAIL: Test failed: {e}")
