import os
import sys
import json
import urllib.parse
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv

load_dotenv()

class GoogleDriveManager:
    """
    Класс для управления синхронизацией файлов с Google Drive.
    Поддерживает авторизацию через Service Account (рекомендуется), OAuth User Token и API Key.
    Реализует абстрактные пути хранения по протоколу storage://
    """
    def __init__(self, creds_path=None, api_key_path=None, root_folder_id=None):
        self.creds_path = creds_path or os.getenv("GDRIVE_SERVICE_ACCOUNT_FILE", "configs/service_account.json")
        self.api_key_path = api_key_path or os.getenv("GDRIVE_API_KEY_FILE", "configs/google_api_key.txt")
        self.root_folder_id = root_folder_id or os.getenv("GDRIVE_ROOT_FOLDER_ID", "14TJcFokq6mxGh3vy0rBvfAFLQ6ewCjH5")
        self.service = self._authenticate()
        
        # Кэш для ID папок, чтобы не запрашивать API постоянно
        self._folder_cache = {}

    def _authenticate(self):
        """
        Выполняет многоуровневую авторизацию:
        1. Сервисный аккаунт (Service Account) из JSON-файла.
        2. OAuth User Token (token.json).
        3. Google API Key (developerKey) для публичных операций.
        """
        # Попытка 1: Сервисный аккаунт JSON
        if os.path.exists(self.creds_path):
            try:
                with open(self.creds_path, 'r', encoding='utf-8') as f:
                    creds_data = json.load(f)
                if creds_data.get("type") == "service_account":
                    print(f"[INFO] Avtorizatsiya: Servisniy akkaunt ({creds_data.get('client_email')})")
                    credentials = service_account.Credentials.from_service_account_info(
                        creds_data,
                        scopes=['https://www.googleapis.com/auth/drive']
                    )
                    return build('drive', 'v3', credentials=credentials)
            except Exception as e:
                print(f"[WARN] Oshibka avtorizatsii cherez Service Account: {e}. Probuyem drugiye metody...")

        # Попытка 2: OAuth 2.0 User Token (token.json в корне или configs)
        token_paths = ['token.json', 'configs/token.json']
        for tp in token_paths:
            if os.path.exists(tp):
                try:
                    print(f"[INFO] Avtorizatsiya: Polzovatelskiy token ({tp})")
                    credentials = Credentials.from_authorized_user_file(
                        tp, 
                        scopes=['https://www.googleapis.com/auth/drive']
                    )
                    return build('drive', 'v3', credentials=credentials)
                except Exception as e:
                    print(f"[WARN] Oshibka avtorizatsii cherez token {tp}: {e}")

        # Попытка 3: API Key (например, для публичного чтения)
        if os.path.exists(self.api_key_path):
            try:
                with open(self.api_key_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                api_key = ""
                for line in lines:
                    line = line.strip()
                    if line.startswith("AIzaSy"):
                        api_key = line
                        break
                    elif "export GOOGLE_API_KEY=" in line:
                        # Парсим из строки экспорта
                        parts = line.split("GOOGLE_API_KEY=")
                        if len(parts) > 1:
                            api_key = parts[1].split()[0].replace("'", "").replace('"', '')
                            break
                if api_key:
                    print(f"[INFO] Avtorizatsiya: Google API Key (developerKey)")
                    return build('drive', 'v3', developerKey=api_key)
            except Exception as e:
                print(f"[WARN] Oshibka avtorizatsii cherez API Key: {e}")

        # Попытка 4: API Key из переменной окружения
        env_api_key = os.getenv("GOOGLE_API_KEY")
        if env_api_key:
            try:
                print(f"[INFO] Avtorizatsiya: Google API Key iz okruzheniya (developerKey)")
                return build('drive', 'v3', developerKey=env_api_key)
            except Exception as e:
                print(f"[WARN] Oshibka avtorizatsii cherez GOOGLE_API_KEY iz okruzheniya: {e}")

        raise ValueError("[ERROR] Ne udalos avtorizovatsya v Google Drive API. Proverte uchetnie dannie.")

    def get_or_create_folder(self, folder_name: str, parent_id: str = None) -> str:
        """
        Ищет папку по имени. Если не находит, создает её.
        Использует кэш для снижения нагрузки на API.
        """
        cache_key = f"{folder_name}:{parent_id or 'root'}"
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"
        else:
            query += f" and 'root' in parents"

        try:
            results = self.service.files().list(q=query, spaces='drive', fields='files(id)').execute()
            items = results.get('files', [])
            
            if items:
                folder_id = items[0]['id']
            else:
                # Создаем папку
                folder_metadata = {
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                if parent_id:
                    folder_metadata['parents'] = [parent_id]
                
                folder = self.service.files().create(body=folder_metadata, fields='id').execute()
                folder_id = folder.get('id')
                print(f"[INFO] Sozdana novaya papka na Diske: {folder_name} (ID: {folder_id})")

            self._folder_cache[cache_key] = folder_id
            return folder_id
        except Exception as e:
            print(f"[ERROR] Oshibka polucheniya/sozdaniya papki {folder_name}: {e}")
            raise

    def resolve_storage_uri(self, storage_uri: str) -> tuple[str, str]:
        """
        Разрешает абстрактный URI storage:// в тип папки и имя файла.
        Пример: storage://slices/page_01.webp -> ('slices', 'page_01.webp')
        """
        if not storage_uri.startswith("storage://"):
            raise ValueError(f"Nekorrektniy protokol hraneniya: {storage_uri}. Ozhidaetsya storage://")
        
        path = storage_uri[len("storage://"):]
        parts = path.split('/', 1)
        if len(parts) < 2:
            return "general", parts[0]
        return parts[0], parts[1]

    def _get_target_folder_id(self, folder_type: str) -> str:
        """
        Сопоставляет абстрактный тип папки с физической папкой на Google Drive.
        """
        # Карта соответствия типов папок и их названий на Диске
        folder_mapping = {
            "slices": "Slices",
            "office": "Office_Docs",
            "schematics": "Schematics",
            "originals": "Originals",
            "quarantine": "Quarantine_Lake"
        }
        
        dir_name = folder_mapping.get(folder_type.lower(), folder_type)
        return self.get_or_create_folder(dir_name, self.root_folder_id)

    def upload_file(self, local_path: str, target_folder_id: str, mime_type: str = None) -> dict:
        """
        Базовый метод загрузки локального файла в указанную папку Google Drive.
        """
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Lokalniy fail ne nayden: {local_path}")
            
        file_name = os.path.basename(local_path)
        file_metadata = {
            'name': file_name,
            'parents': [target_folder_id]
        }
        
        media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
        try:
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink'
            ).execute()
            print(f"[INFO] Uspeshno zagruzhen fail: {file_name} -> Google Drive (ID: {file.get('id')})")
            return file
        except Exception as e:
            print(f"[ERROR] Oshibka pri zagruzke faila {file_name} na Google Drive: {e}")
            raise

    def upload_by_uri(self, storage_uri: str, local_path: str, mime_type: str = None) -> str:
        """
        Загружает файл на Google Drive, используя абстрактный URI.
        Возвращает Google Drive File ID.
        """
        folder_type, file_name = self.resolve_storage_uri(storage_uri)
        target_folder_id = self._get_target_folder_id(folder_type)
        
        # Выполняем загрузку
        file_info = self.upload_file(local_path, target_folder_id, mime_type)
        return file_info.get('id')

    def download_file(self, file_id: str, local_dest_path: str) -> bool:
        """
        Базовый метод скачивания файла с Google Drive по его ID.
        """
        try:
            request = self.service.files().get_media(fileId=file_id)
            os.makedirs(os.path.dirname(local_dest_path), exist_ok=True)
            
            with open(local_dest_path, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
            print(f"[INFO] Uspeshno skachan fail s Google Drive (ID: {file_id}) -> {local_dest_path}")
            return True
        except Exception as e:
            print(f"[ERROR] Oshibka skachivaniya faila po ID {file_id}: {e}")
            return False

    def download_by_uri(self, storage_uri: str, local_dest_path: str, gdrive_file_id: str = None) -> bool:
        """
        Скачивает файл по его абстрактному URI. Если gdrive_file_id не указан, пытается найти файл по имени.
        """
        if gdrive_file_id:
            return self.download_file(gdrive_file_id, local_dest_path)
            
        folder_type, file_name = self.resolve_storage_uri(storage_uri)
        target_folder_id = self._get_target_folder_id(folder_type)
        
        # Ищем файл по имени в целевой папке
        query = f"name='{file_name}' and '{target_folder_id}' in parents and trashed=false"
        try:
            results = self.service.files().list(q=query, spaces='drive', fields='files(id)').execute()
            items = results.get('files', [])
            if not items:
                print(f"[WARN] Fail {file_name} ne nayden v papke {folder_type} na Google Drive.")
                return False
            
            file_id = items[0]['id']
            return self.download_file(file_id, local_dest_path)
        except Exception as e:
            print(f"[ERROR] Oshibka pri poiske i skachivanii faila {file_name}: {e}")
            return False

if __name__ == '__main__':
    # Блок быстрого тестирования модуля
    print("--- TEST MODULYA GDRIVE_SYNC ---")
    try:
        # Проверяем работу парсера URI
        gdm = GoogleDriveManager()
        print("INFO: Initsializatsiya menedzhera vypolnena!")
        uri = "storage://slices/test_doc_p10.md"
        folder, name = gdm.resolve_storage_uri(uri)
        print(f"INFO: Test parsinga URI: {uri} -> Papka: '{folder}', Fail: '{name}'")
    except Exception as e:
        print(f"ERROR: Test provalen: {e}")
