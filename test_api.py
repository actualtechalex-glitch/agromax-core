import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive']

def main():
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        service = build('drive', 'v3', credentials=creds)
        try:
            about = service.about().get(fields="user").execute()
            print(f"\n✅ ОТЛИЧНО! Токен рабочий.")
            print(f"✅ Доступ к личной базе Google Drive открыт. Аккаунт: {about['user']['emailAddress']}")
        except Exception as e:
            print(f"\n❌ Ошибка токена: {e}. Возможно, он устарел или был отозван.")
    else:
        print("\n❌ Файл token.json не найден в текущей директории.")

if __name__ == '__main__':
    main()
