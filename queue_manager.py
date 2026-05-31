import os
import json
import redis
from dotenv import load_dotenv

load_dotenv()

class QueueManager:
    """
    Класс для управления очередями задач на базе Redis.
    Использует пул соединений для оптимизации сетевых ресурсов.
    """
    def __init__(self, host=None, port=None, db=None):
        self.host = host or os.getenv("REDIS_HOST", "127.0.0.1")
        self.port = int(port or os.getenv("REDIS_PORT", "6379"))
        self.db = int(db or os.getenv("REDIS_DB", "0"))
        
        # Настройка пула соединений
        self.pool = redis.ConnectionPool(
            host=self.host,
            port=self.port,
            db=self.db,
            decode_responses=True # Автоматически декодируем байты в строки
        )
        self.r = redis.Redis(connection_pool=self.pool)

    def push_task(self, queue_name: str, task_data: dict) -> bool:
        """
        Добавляет задачу в очередь (в левый конец списка - LPUSH).
        """
        try:
            serialized_data = json.dumps(task_data)
            self.r.lpush(queue_name, serialized_data)
            return True
        except Exception as e:
            print(f"[ERROR] QueueManager: Ne udalos dobavit zadachu v ochered {queue_name}: {e}")
            return False

    def pop_task(self, queue_name: str, timeout: int = 0) -> dict | None:
        """
        Извлекает задачу из очереди (с правого конца списка - BRPOP) с блокировкой.
        timeout = 0 означает бесконечное ожидание.
        """
        try:
            # brpop возвращает кортеж: (имя_очереди, значение) или None при таймауте
            result = self.r.brpop(queue_name, timeout=timeout)
            if result:
                _, task_json = result
                return json.loads(task_json)
            return None
        except Exception as e:
            print(f"[ERROR] QueueManager: Oshibka izvlecheniya zadachi is ocheredi {queue_name}: {e}")
            return None

    def get_len(self, queue_name: str) -> int:
        """
        Возвращает количество задач в очереди.
        """
        try:
            return self.r.llen(queue_name)
        except Exception as e:
            print(f"[ERROR] QueueManager: Oshibka polucheniya dliny ocheredi {queue_name}: {e}")
            return 0

    def clear(self, queue_name: str) -> bool:
        """
        Полностью очищает очередь.
        """
        try:
            self.r.delete(queue_name)
            return True
        except Exception as e:
            print(f"[ERROR] QueueManager: Oshibka ochistki ocheredi {queue_name}: {e}")
            return False

if __name__ == '__main__':
    print("--- TEST QUEUE_MANAGER ---")
    try:
        qm = QueueManager()
        test_queue = "queue:test_system"
        qm.clear(test_queue)
        
        test_data = {"id": 999, "action": "verify_queue"}
        print(f"[INFO] Pushing test task: {test_data}")
        qm.push_task(test_queue, test_data)
        
        len_q = qm.get_len(test_queue)
        print(f"[INFO] Queue length: {len_q}")
        
        print("[INFO] Popping task with brpop...")
        popped = qm.pop_task(test_queue, timeout=2)
        print(f"[INFO] Popped task: {popped}")
        
        if popped and popped.get("id") == 999:
            print("INFO: Test proyden uspeshno!")
        else:
            print("ERROR: Test provalen - nekorrektnie dannie.")
            
        qm.clear(test_queue)
    except Exception as e:
        print(f"[ERROR] Sistemnaya oshibka testa: {e}")
