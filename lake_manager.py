import os
import glob
import json
from dotenv import load_dotenv

load_dotenv()

class LakeManager:
    """
    Менеджер Озера данных (Medallion Data Lake) для Agromax v6.4.
    Инкапсулирует логику работы со слоями Bronze (сырые данные) и Silver (чистые данные RAG).
    Обеспечивает поддержку абстрактных URI вида storage://bronze/... и storage://silver/...
    """
    def __init__(self, bronze_dir=None, silver_dir=None):
        self.bronze_dir = bronze_dir or os.getenv("LAKE_BRONZE_DIR", "lake/bronze")
        self.silver_dir = silver_dir or os.getenv("LAKE_SILVER_DIR", "lake/silver")
        
        # Создаем директории, если они отсутствуют
        os.makedirs(self.bronze_dir, exist_ok=True)
        os.makedirs(self.silver_dir, exist_ok=True)

    def save_to_bronze(self, task_id: str, raw_data: bytes | str, file_ext: str) -> str:
        """
        Сохраняет сырые данные в Bronze слой.
        Возвращает абстрактный URI: storage://bronze/{task_id}{ext}
        """
        if not file_ext.startswith('.'):
            file_ext = '.' + file_ext
            
        file_name = f"{task_id}{file_ext}"
        physical_path = os.path.join(self.bronze_dir, file_name)
        
        mode = 'wb' if isinstance(raw_data, bytes) else 'w'
        encoding = None if isinstance(raw_data, bytes) else 'utf-8'
        
        with open(physical_path, mode, encoding=encoding) as f:
            f.write(raw_data)
            
        print(f"[INFO] LakeManager: Spaseno v Bronze -> {file_name}")
        return f"storage://bronze/{file_name}"

    def get_from_bronze(self, task_id: str) -> tuple[bytes, str] | None:
        """
        Находит и считывает сырые данные из Bronze слоя по task_id.
        Возвращает кортеж (данные_bytes, расширение_файла) или None.
        """
        # Ищем любой файл, начинающийся с task_id в папке Bronze
        pattern = os.path.join(self.bronze_dir, f"{task_id}.*")
        found_files = glob.glob(pattern)
        
        if not found_files:
            print(f"[WARN] LakeManager: Fail dlya Task ID {task_id} ne nayden v Bronze.")
            return None
            
        physical_path = found_files[0]
        file_ext = os.path.splitext(physical_path)[1]
        
        with open(physical_path, 'rb') as f:
            data = f.read()
            
        return data, file_ext

    def save_to_silver(self, task_id: str, cleansed_data: str | dict, is_json: bool = False) -> str:
        """
        Сохраняет очищенные валидные данные (Markdown или JSON) в Silver слой.
        Возвращает абстрактный URI: storage://silver/{task_id}.md или .json
        """
        if isinstance(cleansed_data, dict) or is_json:
            file_ext = ".json"
            file_name = f"{task_id}{file_ext}"
            physical_path = os.path.join(self.silver_dir, file_name)
            with open(physical_path, 'w', encoding='utf-8') as f:
                json.dump(cleansed_data, f, ensure_ascii=False, indent=2)
        else:
            file_ext = ".md"
            file_name = f"{task_id}{file_ext}"
            physical_path = os.path.join(self.silver_dir, file_name)
            with open(physical_path, 'w', encoding='utf-8') as f:
                f.write(str(cleansed_data))
                
        print(f"[INFO] LakeManager: Spaseno v Silver -> {file_name}")
        return f"storage://silver/{file_name}"

    def get_from_silver(self, task_id: str) -> str | dict | None:
        """
        Находит и считывает чистые данные из Silver слоя по task_id.
        Если файл в формате JSON, автоматически парсит его в dict.
        """
        # Сначала ищем JSON, затем MD
        json_path = os.path.join(self.silver_dir, f"{task_id}.json")
        md_path = os.path.join(self.silver_dir, f"{task_id}.md")
        
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        elif os.path.exists(md_path):
            with open(md_path, 'r', encoding='utf-8') as f:
                return f.read()
                
        print(f"[WARN] LakeManager: Fail dlya Task ID {task_id} ne nayden v Silver.")
        return None

if __name__ == '__main__':
    print("--- TEST LAKE_MANAGER ---")
    lm = LakeManager()
    
    # 1. Тест Bronze
    bronze_uri = lm.save_to_bronze("test_task_123", b"raw binary manual contents", ".pdf")
    print(f"Bronze URI: {bronze_uri}")
    
    res = lm.get_from_bronze("test_task_123")
    if res:
        raw, ext = res
        print(f"Retrieved from Bronze: {raw} | Ext: {ext}")
    
    # 2. Тест Silver
    silver_uri_md = lm.save_to_silver("test_task_123", "# Cleaned Markdown Segment\nSome tractor parts text...")
    print(f"Silver MD URI: {silver_uri_md}")
    
    silver_uri_json = lm.save_to_silver("test_task_123_metadata", {"author": "AI", "pages": 15}, is_json=True)
    print(f"Silver JSON URI: {silver_uri_json}")
    
    cleansed_md = lm.get_from_silver("test_task_123")
    print(f"Retrieved MD: {cleansed_md}")
    
    cleansed_json = lm.get_from_silver("test_task_123_metadata")
    print(f"Retrieved JSON: {cleansed_json}")
