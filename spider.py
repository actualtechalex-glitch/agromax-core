import asyncio
import os
import hashlib
import psycopg2
from playwright.async_api import async_playwright
from dotenv import load_dotenv
from queue_manager import QueueManager


load_dotenv()

# === КОНФИГУРАЦИЯ ПОДКЛЮЧЕНИЯ ===
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": "5432",
    "database": "agromax_state",
    "user": "agromax_user",
    "password": "AgromaxStrongPassword2026"
}

BASE_URL = "https://dealers.rostselmash.com"
LOGIN_URL = f"{BASE_URL}/auth/"
CATALOG_URL = f"{BASE_URL}/department-service/?SIZEN_1=20&PAGEN_1="

def get_hash(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()

async def run_spider():
    print("=== Запуск Spider-Scout v35.7 (Точечный инкрементальный сбор) ===")
    
    login = os.getenv('PORTAL_LOGIN')
    password = os.getenv('PORTAL_PASSWORD')

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cursor = conn.cursor()
    qm = QueueManager()


    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        print(">>> Авторизация на портале завода...")
        await page.goto(LOGIN_URL)
        await page.fill('input[name="USER_LOGIN"]', login if login else "")
        await page.fill('input[name="USER_PASSWORD"]', password if password else "")
        await page.keyboard.press("Enter")

        await asyncio.sleep(5)

        current_page = 1
        incremental_stop_triggered = False

        while True:
            print(f">>> Сканирование страницы {current_page}...", end=" ", flush=True)
            await page.goto(f"{CATALOG_URL}{current_page}")
            await asyncio.sleep(2)  # Пауза для подгрузки элементов

            # Собираем СТРОГО ссылки (тег <a>), без огромных родительских DIV-оберток
            all_links = await page.locator('a').all()
            
            # Фильтруем ссылки, которые содержат текст скачивания
            target_links = []
            for link in all_links:
                try:
                    text = await link.inner_text()
                    if "скачать" in text.lower():
                        target_links.append(link)
                except:
                    continue

            if not target_links:
                print("Страницы каталога закончились. Поиск завершен.")
                break

            new_added = 0

            for link in target_links:
                try:
                    url = await link.get_attribute('href')
                    if not url or url == '#':
                        continue
                        
                    full_url = f"{BASE_URL}{url}" if url.startswith('/') else url
                    h = get_hash(full_url)

                    # Проверяем инкрементальный стоп (были ли мы тут в прошлый раз)
                    cursor.execute("SELECT id FROM public.slices_registry WHERE parent_file_hash = %s LIMIT 1;", (h,))
                    if cursor.fetchone():
                        print(f"\n\n🎯 Паук уперся в границу прошлого запуска!")
                        print("Дальнейший поиск остановлен, новые документы отсутствуют.")
                        incremental_stop_triggered = True
                        break

                    # Умное извлечение названия мануала из соседних блоков
                    title = await link.evaluate("""
                        (node) => {
                            let container = node.closest('.item, .row, tr, [class*="item"], [class*="row"], li, td, .middle');
                            if (container) {
                                let titleEl = container.querySelector('.title, .name, [class*="title"], [class*="name"], h3, h4');
                                if (titleEl && titleEl.innerText.trim()) return titleEl.innerText.trim();
                                
                                let lines = container.innerText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                                let clean = lines.filter(l => !l.includes('СКАЧАТЬ') && !l.includes('Мб') && !/^\\d{2}\\.\\d{2}/.test(l));
                                if (clean.length > 0) return clean[0];
                            }
                            return 'Инструкция Ростсельмаш';
                        }
                    """)

                    # Запись коренной ссылки в базу данных с получением ID
                    insert_query = """
                        INSERT INTO public.slices_registry (parent_file_hash, file_name, slice_uri, ai_status)
                        VALUES (%s, %s, %s, 'QUEUED') RETURNING id;
                    """
                    cursor.execute(insert_query, (h, title, full_url))
                    inserted_id = cursor.fetchone()[0]
                    
                    # Отправка задачи в Redis
                    qm.push_task("queue:transit", {
                        "id": inserted_id,
                        "slice_uri": full_url,
                        "physical_path": None,
                        "file_name": title
                    })
                    new_added += 1
                except Exception as e:
                    print(f"[ERROR] Oshibka dobavleniya taska: {e}")
                    continue

            print(f"Найдено документов: {len(target_links)}, Импортировано новых: {new_added}")

            if incremental_stop_triggered:
                break

            current_page += 1

        await browser.close()
        
        cursor.execute("SELECT count(*) FROM public.slices_registry;")
        print(f"\n🎉 Сбор окончен! Всего коренных мануалов в чистой базе: {cursor.fetchone()[0]} шт.")
        
        cursor.close()
        conn.close()

if __name__ == "__main__":
    asyncio.run(run_spider())
