import os
import sys
import shutil
import requests
import psycopg2
import urllib.parse
import zipfile
import hashlib
from psycopg2.extras import RealDictCursor
from queue_manager import QueueManager
from logger_manager import audit_task
from lake_manager import LakeManager

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": "5432",
    "database": "agromax_state",
    "user": "agromax_user",
    "password": "AgromaxStrongPassword2026"
}

# Директории монтирования GDrive (оставлены для совместимости)
MOUNT_BASE = "/mnt/gdrive/AGROMAX_Knowledge_Base"
PATH_SLICES = os.path.join(MOUNT_BASE, "Slices")
PATH_OFFICE = os.path.join(MOUNT_BASE, "Office_Docs")
PATH_SCHEMATICS = os.path.join(MOUNT_BASE, "Schematics")
PATH_ORIGINALS = os.path.join(MOUNT_BASE, "Originals")
TMP_DIR = "/tmp/agromax_transit"

SOFTWARE_EXTENSIONS = ['.exe', '.bin', '.hex', '.msi', '.apk', '.bat', '.cmd', '.iso', '.sys', '.dll', '.rom', '.dat', '.edc', '.txt']
KEYWORDS_SCHEMATICS = ['схема', 'чертеж', 'blueprint', 'schematic', 'wiring', 'hydraulic', 'электросхема', 'гидравл', 'электр', 'нар', 'г3', 'э3']

def init_transit():
    for p in [PATH_SLICES, PATH_OFFICE, PATH_SCHEMATICS, PATH_ORIGINALS, TMP_DIR]:
        os.makedirs(p, exist_ok=True)

def get_real_filename(url, db_title):
    parsed_url = urllib.parse.urlparse(url)
    base_name = os.path.basename(parsed_url.path)
    ext = os.path.splitext(base_name)[1].lower()
    
    if not ext: ext = ".pdf"
    base_name_clean = urllib.parse.unquote(base_name)
        
    invalid_chars = '<>:"/\\|?*'
    safe_title = ''.join(c for c in db_title if c not in invalid_chars).strip()
    
    # ЖЕСТКАЯ БЛОКИРОВКА ШАБЛОНА: Если имя пустое или дефолтное, берем реальное имя файла из URL
    if not safe_title or "инструкция ростсельмаш" in safe_title.lower():
        return base_name_clean if base_name_clean else f"manual_doc_{os.urandom(4).hex()}{ext}"
    
    if safe_title.lower().endswith(ext):
        return safe_title
    return f"{safe_title}{ext}"

def download_file(url, dest_path):
    try:
        if url.startswith('storage://'):
            parsed = urllib.parse.urlparse(url)
            path_parts = parsed.path.strip('/').split('/')
            if len(path_parts) >= 2:
                layer = path_parts[0]  # bronze or silver
                filename = path_parts[1]
                task_id = os.path.splitext(filename)[0]
                
                lm = LakeManager()
                if layer == 'bronze':
                    res = lm.get_from_bronze(task_id)
                    if res:
                        raw_data, _ = res
                        with open(dest_path, 'wb') as f:
                            f.write(raw_data)
                        return True
                elif layer == 'silver':
                    cleansed_data = lm.get_from_silver(task_id)
                    if cleansed_data is not None:
                        mode = 'w' if isinstance(cleansed_data, str) else 'wb'
                        encoding = 'utf-8' if isinstance(cleansed_data, str) else None
                        with open(dest_path, mode, encoding=encoding) as f:
                            if isinstance(cleansed_data, dict):
                                json.dump(cleansed_data, f, ensure_ascii=False, indent=2)
                            else:
                                f.write(cleansed_data)
                        return True
            print(f"   [ERROR] Invalid storage URI format: {url}")
            return False

        if url.startswith('file://'):
            path_str = url[7:]
            path_str = urllib.parse.unquote(path_str)
            path_str = os.path.normpath(path_str)
            
            if os.name == 'nt':
                if path_str.startswith('\\') and len(path_str) > 2 and path_str[2] == ':':
                    path_str = path_str[1:]
                elif path_str.startswith('\\\\'):
                    single_slash_path = path_str[1:]
                    if not os.path.exists(path_str) and os.path.exists(single_slash_path):
                        path_str = single_slash_path
            
            shutil.copy(path_str, dest_path)
            return True
            
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, stream=True, timeout=60, headers=headers)
        response.raise_for_status()
        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"   [ERROR] Oshibka skachivaniya: {e}")
        return False

def route_file(file_path, file_name, db_title, lm, task_id):
    ext = os.path.splitext(file_name)[1].lower()
    search_text = (file_name + " " + db_title).lower()

    if ext in SOFTWARE_EXTENSIONS:
        if os.path.exists(file_path): os.remove(file_path)
        return "SOFTWARE_SKIPPED", "DELETED"

    # Считываем сырые данные для сохранения в Bronze слое
    with open(file_path, 'rb') as f:
        raw_bytes = f.read()

    bronze_uri = lm.save_to_bronze(task_id, raw_bytes, ext)

    if ext in ['.xlsx', '.xls', '.docx', '.doc', '.csv']:
        if os.path.exists(file_path): os.remove(file_path)
        return "OFFICE_DOCS", bronze_uri

    elif ext == '.pdf':
        if any(kw in search_text for kw in KEYWORDS_SCHEMATICS):
            if os.path.exists(file_path): os.remove(file_path)
            return "SCHEMATICS", bronze_uri
        else:
            # Создаем начальное представление в Silver
            cleansed_markdown = f"# {db_title}\n[ORIGINAL BRONZE PATH: {bronze_uri}]\n"
            silver_uri = lm.save_to_silver(task_id, cleansed_markdown)
            
            if os.path.exists(file_path): os.remove(file_path)
            return "SLICES_STUB_CREATED", silver_uri
            
    if os.path.exists(file_path): os.remove(file_path)
    return "UNKNOWN_FORMAT", "DELETED"

def process_zip_archive(archive_path, db_title, lm, parent_task_id):
    extracted_count = 0
    archive_tmp = os.path.join(TMP_DIR, "unpacked_" + os.path.basename(archive_path).replace(' ', '_'))
    os.makedirs(archive_tmp, exist_ok=True)
    
    try:
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            for zinfo in zip_ref.infolist():
                # 🛠 ЛЕЧИМ АБРАКАДАБРУ ИЗ WINDOWS-АРХИВОВ
                try:
                    decoded_name = zinfo.filename.encode('cp437').decode('cp866')
                except:
                    try:
                        decoded_name = zinfo.filename.encode('cp437').decode('windows-1251')
                    except:
                        decoded_name = zinfo.filename
                
                zinfo.filename = decoded_name
                zip_ref.extract(zinfo, archive_tmp)
            
        for root, dirs, files in os.walk(archive_tmp):
            for file in files:
                file_ext = os.path.splitext(file)[1].lower()
                full_ext_path = os.path.join(root, file)
                
                if file_ext in ['.pdf', '.xlsx', '.xls', '.docx', '.doc', '.csv']:
                    sub_id = hashlib.md5(file.encode('utf-8')).hexdigest()[:8]
                    task_id = f"{parent_task_id}_{sub_id}"
                    status_type, final_dest = route_file(full_ext_path, file, file, lm, task_id)
                    if final_dest and final_dest != "DELETED":
                        print(f"      ↳ Izvechen manual: [{status_type}] -> {file}")
                        extracted_count += 1
    except Exception as e:
        print(f"   [ERROR] Sboy vskrytiya arhiva: {e}")
    finally:
        if os.path.exists(archive_tmp):
            shutil.rmtree(archive_tmp)
            
    return extracted_count

@audit_task(worker_name="transit_worker")
def process_single_task(task, cursor, conn):
    uri_to_use = task['slice_uri'] if task['slice_uri'] else task['physical_path']
    db_title = task['file_name']
    ext = os.path.splitext(urllib.parse.urlparse(uri_to_use).path)[1].lower()
    
    real_file_name = get_real_filename(uri_to_use, db_title)
    
    local_tmp_path = os.path.join(TMP_DIR, real_file_name)
    lm = LakeManager()
    
    if download_file(uri_to_use, local_tmp_path):
        if real_file_name.endswith('.zip') or ext == '.zip':
            docs_found = process_zip_archive(local_tmp_path, db_title, lm, str(task['id']))
            status_type = f"EXTRACTED_{docs_found}" if docs_found > 0 else "SOFTWARE_CLEANED"
            final_dest = "DATABASE_SYNCED"
            if os.path.exists(local_tmp_path): os.remove(local_tmp_path)
        else:
            status_type, final_dest = route_file(local_tmp_path, real_file_name, db_title, lm, str(task['id']))
            print(f"    [OK] Razmeschen: [{status_type}] -> {real_file_name}")
        
        cursor.execute("UPDATE public.slices_registry SET ai_status = 'COMPLETED', storage_path = %s, file_type = %s, timestamp_done = NOW() WHERE id = %s;", (final_dest, status_type, task['id']))
        conn.commit()
    else:
        cursor.execute("UPDATE public.slices_registry SET ai_status = 'FAILED', timestamp_done = NOW() WHERE id = %s;", (task['id'],))
        conn.commit()
        raise RuntimeError(f"Failed to download file: {real_file_name}")

def process_pipeline():
    init_transit()
    print("=== Konveyer TRANZIT v35.11 (Anti-Abrakadabra) ===")
    processed_count = 0
    qm = QueueManager()
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        while True:
            task = qm.pop_task("queue:transit", timeout=5)
            
            if not task:
                print(f"\n✅ Ochered pusta! Obrabotano: {processed_count}")
                break
                
            print(f"\n[{processed_count+1}] V rabote ID: {task['id']}")
            try:
                process_single_task(task, cursor, conn)
            except Exception as e:
                print(f"   [ERROR] Oshibka processinga zadachi: {e}")
                
            processed_count += 1

        cursor.close(); conn.close()
    except Exception as e: print(f"\n🚨 OSHIBKA: {e}")

if __name__ == "__main__": process_pipeline()
