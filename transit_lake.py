import os, sys, time, requests, urllib.parse
import psycopg2
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Загружаем пароли из .env
load_dotenv()

TMP_DIR = "/tmp/agromax_lake"
os.makedirs(TMP_DIR, exist_ok=True)

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
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    items = results.get('files', [])
    if items:
        return items[0]['id']
    else:
        meta = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder'}
        if parent_id:
            meta['parents'] = [parent_id]
        return service.files().create(body=meta, fields='id').execute().get('id')

def main():
    print("🌊 ЗАПУСК ИДЕАЛЬНОГО КОНВЕЙЕРА RAW DATA LAKE (v35.12.PRO) 🌊")
    service = get_drive_service()
    
    base_id = get_or_create_folder(service, "AGROMAX_Knowledge_Base")
    lake_id = get_or_create_folder(service, "Raw_Data_Lake", base_id)

    db = get_db()
    
    while True:
        try:
            with db:
                with db.cursor() as cur:
                    cur.execute("""
                        SELECT id, file_name, slice_uri 
                        FROM public.slices_registry 
                        WHERE ai_status = 'PENDING_GEMINI' 
                        FOR UPDATE SKIP LOCKED LIMIT 1;
                    """)
                    row = cur.fetchone()
                    
                    if not row:
                        print("✅ Очередь пуста! Озеро наполнено.")
                        break

                    file_id, db_filename, file_url = row
                    
                    # --- МОДУЛЬ УМНОГО НЕЙМИНГА И ЛЕЧЕНИЯ ИМЕН ---
                    parsed_url = urllib.parse.urlparse(file_url)
                    real_filename = os.path.basename(parsed_url.path)
                    real_filename = urllib.parse.unquote(real_filename)
                    
                    if not real_filename or '.' not in real_filename:
                        real_filename = db_filename if db_filename else f"raw_archive_{file_id}.bin"
                        
                    if "Инструкция Ростсельмаш" in real_filename:
                        real_filename = f"rs_manual_raw_{file_id}.zip"
                        
                    local_path = os.path.join(TMP_DIR, real_filename)
                    
                    print(f"\n[{file_id}] 📥 Качаем в Озеро: {real_filename}")
                    
                    with requests.get(file_url, stream=True, timeout=30) as r:
                        r.raise_for_status()
                        
                        # Если сервер завода отдает имя внутри файла — перехватываем его
                        if "Content-Disposition" in r.headers:
                            cd = r.headers["Content-Disposition"]
                            if "filename=" in cd:
                                header_name = cd.split("filename=")[1].strip('"\'')
                                try:
                                    header_name = header_name.encode('iso-8859-1').decode('utf-8')
                                    real_filename = header_name
                                    local_path = os.path.join(TMP_DIR, real_filename)
                                except:
                                    pass

                        with open(local_path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                    
                    # Загружаем в Озеро
                    media = MediaFileUpload(local_path, resumable=True)
                    file_metadata = {'name': real_filename, 'parents': [lake_id]}
                    service.files().create(body=file_metadata, media_body=media, fields='id').execute()
                    
                    # --- ИСЦЕЛЕНИЕ БАЗЫ ДАННЫХ ---
                    cur.execute("""
                        UPDATE public.slices_registry 
                        SET ai_status = 'COMPLETED', 
                            file_type = 'RAW_LAKE',
                            file_name = %s
                        WHERE id = %s;
                    """, (real_filename, file_id))
                    
                    print(f"   ✓ Успешно залит в Озеро! Имя в БД обновлено.")
                    
                    if os.path.exists(local_path):
                        os.remove(local_path)
                        
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            time.sleep(5)

if __name__ == '__main__':
    main()
