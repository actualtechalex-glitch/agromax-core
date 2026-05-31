import os, sys, json, time
import psycopg2
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

TARGET_FOLDER_ID = "14TJcFokq6mxGh3vy0rBvfAFLQ6ewCjH5"

def get_db():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        dbname=os.getenv('DB_NAME', 'agromax_state'),
        user=os.getenv('DB_USER', 'agromax_user'),
        password=os.getenv('DB_PASS', 'AgromaxStrongPassword2026')
    )

def main():
    print("="*80)
    print("🔄 ПРИВЕДЕНИЕ СУБД К АБСТРАКТНОМУ СТАНДАРТУ СТОРАДЖА (SAL COMPLIANT V5.5) 🔄")
    print("="*80)
    db = get_db()
    try:
        with db:
            with db.cursor() as cur:
                cur.execute("SELECT id, document_id, page_number, ai_metadata FROM public.document_chunks;")
                rows = cur.fetchall()
                print(f"📦 Найдено {len(rows)} записей для исправления в Postgres...")
                updated_count = 0
                
                for chunk_id, doc_id, page_num, metadata in rows:
                    if not metadata: metadata = {}
                    existing_drive_id = metadata.get('google_drive_id') or (metadata.get('storage_locator', {}).get('file_id') if metadata.get('storage_locator') else None)
                    source_model = metadata.get('source', 'pymupdf')
                    
                    filename = f"slice_doc{doc_id}_p{page_num}.webp"
                    abstract_uri = f"storage://slices/{filename}"
                    
                    if not existing_drive_id: existing_drive_id = "NOT_AVAILABLE_LOCAL_LOST"
                    if metadata.get('slice_uri') and isinstance(metadata.get('storage_locator'), dict): continue
                    
                    clean_metadata = {
                        "source": source_model,
                        "slice_uri": abstract_uri,
                        "storage_locator": {
                            "provider": "gdrive",
                            "file_id": existing_drive_id
                        }
                    }
                    cur.execute("UPDATE public.document_chunks SET ai_metadata = %s WHERE id = %s;", (json.dumps(clean_metadata), chunk_id))
                    updated_count += 1
                print(f"✅ Миграция завершена! Переведено на абстрактные URI: {updated_count} строк.")
    except Exception as e:
        print(f"❌ Сбой нормализации базы: {e}")

if __name__ == '__main__':
    main()
