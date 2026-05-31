import os, sys, time
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

OLD_FOLDER_ID = "1wQx8XouK7_1H8LALyFCmxQo6LL5TUdGv"
NEW_FOLDER_ID = "14TJcFokq6mxGh3vy0rBvfAFLQ6ewCjH5"

def get_drive_service():
    creds = Credentials.from_authorized_user_file('token.json', ['https://www.googleapis.com/auth/drive'])
    return build('drive', 'v3', credentials=creds)

def main():
    print("="*80)
    print("🛸 АГРОМАКС: ЗАПУСК ОБЛАЧНОГО ГРУЗЧИКА СЛАЙСОВ (МГНОВЕННЫЙ ПЕРЕНОС) 🛸")
    print("="*80)
    service = get_drive_service()
    page_token = None
    moved_count = 0
    
    while True:
        query = f"'{OLD_FOLDER_ID}' in parents and trashed=false"
        results = service.files().list(
            q=query, spaces='drive', fields='nextPageToken, files(id, name)', pageSize=100, pageToken=page_token
        ).execute()
        
        items = results.get('files', [])
        if not items and moved_count == 0:
            print("📭 Старая папка уже пуста! Переносить нечего.")
            break
            
        for file in items:
            file_id = file['id']
            file_name = file['name']
            service.files().update(
                fileId=file_id, addParents=NEW_FOLDER_ID, removeParents=OLD_FOLDER_ID, fields='id, parents'
            ).execute()
            moved_count += 1
            print(f"   [{moved_count:04d}] Слайс {file_name} -> Перенесен в папку проекта! 🚀")
            
        page_token = results.get('nextPageToken', None)
        if not page_token: break
            
    print("="*80)
    print(f"🎉 ВСЕ ГОТОВО! Перемещено файлов: {moved_count} шт.")
    print("="*80)

if __name__ == '__main__':
    main()
