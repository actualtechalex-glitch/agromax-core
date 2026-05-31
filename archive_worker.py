import os, time, shutil, urllib.parse, zipfile
import psycopg2
import rarfile
import py7zr
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

load_dotenv()
rarfile.UNRAR_TOOL = "unrar"

TMP_DIR = "/tmp/agromax_archives"
EXTRACT_DIR = "/tmp/agromax_extracted"
os.makedirs(TMP_DIR, exist_ok=True)
os.makedirs(EXTRACT_DIR, exist_ok=True)

def get_db():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        dbname=os.getenv('DB_NAME', 'agromax_state'),
        user=os.getenv('DB_USER', 'agromax_user'),
        password=os.getenv('DB_PASS', 'AgromaxStrongPassword2026')
    )

def get_drive_service():
    creds = Credentials.from_authorized_user_file('token.json', ['https://www.googleapis.com/auth/drive'])
    return build('drive', 'v3', credentials=creds)

def get_or_create_folder(service, folder_name, parent_id=None):
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id: query += f" and '{parent_id}' in parents"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    if results.get('files'): return results.get('files')[0]['id']
    return service.files().create(body={'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent_id] if parent_id else []}, fields='id').execute().get('id')

def find_file_by_name(service, filename, folder_id):
    query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields='files(id)').execute()
    return results.get('files', [])[0]['id'] if results.get('files') else None

def smart_routing(filename, folders):
    lower_name = filename.lower()
    if any(x in lower_name for x in ['.doc', '.xls', '.xlsx', '.docx']): return folders['Office_Docs'], 'OFFICE_DOCS'
    elif any(x in lower_name for x in ['схема', 'схемы', 'электрич', 'гидравл', 'dwg']): return folders['Schematics'], 'SCHEMATICS'
    elif lower_name.endswith('.pdf'): return folders['Originals'], 'SLICES_STUB_CREATED'
    elif lower_name.endswith(('.mp4', '.avi', '.mov')): return folders['Originals'], 'PENDING_WHISPER'
    return None, None

def move_to_quarantine(service, file_id, quarantine_folder_id):
    file = service.files().get(fileId=file_id, fields='parents').execute()
    prev_parents = ",".join(file.get('parents', []))
    service.files().update(fileId=file_id, addParents=quarantine_folder_id, removeParents=prev_parents, fields='id, parents').execute()

def main():
    print("🗜 ЗАПУСК ВОРКЕРА АРХИВОВ (v35.14 - ПОДДЕРЖКА ZIP) 🗜")
    service = get_drive_service()
    
    base_id = get_or_create_folder(service, "AGROMAX_Knowledge_Base")
    lake_id = get_or_create_folder(service, "Raw_Data_Lake", base_id)
    quarantine_id = get_or_create_folder(service, "Quarantine_Lake", base_id)
    
    folders = {
        'Originals': get_or_create_folder(service, "Originals", base_id),
        'Schematics': get_or_create_folder(service, "Schematics", base_id),
        'Office_Docs': get_or_create_folder(service, "Office_Docs", base_id)
    }

    db = get_db()
    
    while True:
        try:
            with db:
                with db.cursor() as cur:
                    cur.execute("SELECT id, file_name, slice_uri FROM public.slices_registry WHERE ai_status = 'PENDING_ARCHIVE' FOR UPDATE SKIP LOCKED LIMIT 1;")
                    row = cur.fetchone()
                    
                    if not row:
                        print("✅ Очередь архивов пуста!")
                        break

                    arch_id, db_filename, file_url = row
                    if file_url:
                        arch_name = urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(file_url).path))
                    else:
                        arch_name = db_filename
                        
                    print(f"\n[{arch_id}] 📦 Вскрываем архив: {arch_name}")
                    
                    file_drive_id = find_file_by_name(service, arch_name, lake_id)
                    if not file_drive_id:
                        cur.execute("UPDATE public.slices_registry SET ai_status = 'ERROR_NOT_FOUND' WHERE id = %s", (arch_id,))
                        continue
                        
                    local_arch_path = os.path.join(TMP_DIR, arch_name)
                    ext_path = os.path.join(EXTRACT_DIR, str(arch_id))
                    
                    try:
                        request = service.files().get_media(fileId=file_drive_id)
                        with open(local_arch_path, 'wb') as fh:
                            downloader = MediaIoBaseDownload(fh, request)
                            done = False
                            while not done: _, done = downloader.next_chunk()
                        
                        os.makedirs(ext_path, exist_ok=True)
                        extracted_files = []
                        if arch_name.lower().endswith('.rar'):
                            with rarfile.RarFile(local_arch_path) as rf:
                                rf.extractall(ext_path)
                                extracted_files = rf.namelist()
                        elif arch_name.lower().endswith('.7z'):
                            with py7zr.SevenZipFile(local_arch_path, mode='r') as zf:
                                zf.extractall(path=ext_path)
                                extracted_files = zf.getnames()
                        elif arch_name.lower().endswith('.zip'):
                            with zipfile.ZipFile(local_arch_path, 'r') as zf:
                                zf.extractall(ext_path)
                                extracted_files = zf.namelist()
                                
                        for e_name in extracted_files:
                            full_path = os.path.join(ext_path, e_name)
                            if os.path.isdir(full_path): continue 
                            
                            real_name = os.path.basename(e_name)
                            target_folder_id, category = smart_routing(real_name, folders)
                            
                            if target_folder_id:
                                print(f"   ↳ 🎁 Извлечен: [{category}] -> {real_name}")
                                media = MediaFileUpload(full_path, resumable=True)
                                service.files().create(body={'name': real_name, 'parents': [target_folder_id]}, media_body=media, fields='id').execute()
                                
                                actual_status = 'PENDING_WHISPER' if category == 'PENDING_WHISPER' else 'COMPLETED'
                                cur.execute("INSERT INTO public.slices_registry (parent_id, file_name, file_type, ai_status) VALUES (%s, %s, %s, %s)", 
                                            (arch_id, real_name, category, actual_status))
                                
                        cur.execute("UPDATE public.slices_registry SET ai_status = 'ARCHIVE_UNPACKED' WHERE id = %s", (arch_id,))
                        
                    except Exception as ex:
                        print(f"☣️ КРИТИЧЕСКИЙ СБОЙ АРХИВА: В Карантин! Ошибка: {ex}")
                        cur.execute("UPDATE public.slices_registry SET ai_status = 'QUARANTINED', error_log = %s WHERE id = %s", (str(ex), arch_id))
                        if quarantine_id: move_to_quarantine(service, file_drive_id, quarantine_id)
                        
                    finally:
                        if os.path.exists(local_arch_path): os.remove(local_arch_path)
                        if os.path.exists(ext_path): shutil.rmtree(ext_path, ignore_errors=True)
                        
        except Exception as e:
            print(f"❌ Ошибка конвейера: {e}")
            time.sleep(5)

if __name__ == '__main__':
    main()
