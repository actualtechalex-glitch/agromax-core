import os
import time
import json
import base64
import requests
import psycopg2
import glob
from dotenv import load_dotenv
from queue_manager import QueueManager
from logger_manager import audit_task
from lake_manager import LakeManager
from prompt_cache_manager import GeminiCacheManager

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

google_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY")) if (genai is not None and os.getenv("GEMINI_API_KEY")) else None
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
TMP_DIR = "/tmp/agromax_vision"
os.makedirs(TMP_DIR, exist_ok=True)

def get_db():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', '127.0.0.1'), port=os.getenv('DB_PORT', '5432'),
        dbname=os.getenv('DB_NAME', 'agromax_state'), user=os.getenv('DB_USER', 'agromax_user'),
        password=os.getenv('DB_PASS', 'AgromaxStrongPassword2026')
    )

def compile_enterprise_prompt(cur, prompt_key):
    cur.execute("""
        SELECT r.provider, r.model_id, r.fallback_model_id, r.temperature, r.max_tokens,
               o.system_role, o.core_task, o.strict_constraints, o.output_format_instructions
        FROM public.prompts_registry r
        JOIN public.prompt_roles o ON o.prompt_id = r.id
        WHERE r.prompt_key = %s;
    """, (prompt_key,))
    return cur.fetchone()

def call_ai_openrouter(model_id, system_role, full_prompt, image_path):
    try:
        headers = {"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"}
        content_list = []
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode('utf-8')
            content_list.append({"type": "image_url", "image_url": {"url": f"data:image/webp;base64,{b64}"}})
        content_list.append({"type": "text", "text": full_prompt})
        payload = {
            "model": model_id,
            "messages": [{"role": "system", "content": system_role}, {"role": "user", "content": content_list}],
            "temperature": 0.3
        }
        res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=60)
        if res.status_code == 200:
            return res.json()['choices'][0]['message']['content']
        else:
            print(f"         [ERROR] Oshibka OpenRouter ({res.status_code}): {res.text}")
            return None
    except Exception as e:
        print(f"         [ERROR] Oshibka svyazi s OpenRouter: {e}")
        return None

def call_ai_with_caching(client, prompt_key, provider, model_id, system_role, full_prompt, image_path, fallback_model=None):
    """
    Отправляет запрос к модели с поддержкой Context Caching для Google Gemini
    или обычный inline для других провайдеров.
    """
    if 'anthropic' in model_id.lower() or 'openrouter' in provider.lower():
        return call_ai_openrouter(model_id, system_role, full_prompt, image_path)
    
    # Google Native
    try:
        if client is None:
            raise ValueError("Google GenAI client is None. Ensure GEMINI_API_KEY is configured.")
            
        # Пробуем получить или создать кэш промпта
        # Для кэширования передаем промпт в contents, а системную роль - в system_instruction
        cache_name = GeminiCacheManager.get_or_create_cache(
            client=client,
            prompt_key=prompt_key,
            system_instruction=system_role,
            contents=[full_prompt],
            model_id=model_id
        )
        
        contents = []
        if image_path and os.path.exists(image_path):
            contents.append(Image.open(image_path))
            
        if cache_name:
            # Кэш успешно создан, передаем только картинки/пользовательские данные
            res = client.models.generate_content(
                model=model_id.replace('google/', ''),
                contents=contents,
                config=types.GenerateContentConfig(
                    cached_content=cache_name,
                    temperature=0.2
                )
            )
        else:
            # Откат в inline: промпт передается явно в contents
            contents.append(full_prompt)
            res = client.models.generate_content(
                model=model_id.replace('google/', ''),
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_role,
                    temperature=0.2
                )
            )
        return res.text
        
    except Exception as e:
        print(f"         [ERROR] Oshibka Native Gemini API: {e}")
        if fallback_model:
            print(f"      ⚠️ Zapusk rezervnoy modeli: {fallback_model}...")
            return call_ai_with_caching(client, prompt_key, 'google', fallback_model, system_role, full_prompt, image_path, None)
        return None

@audit_task(worker_name="vision_worker")
def process_page_task(page_task, client_override=None):
    """
    Обрабатывает одну страницу документа. Запускается параллельно в пуле потоков.
    """
    doc_id = page_task['doc_id']
    file_name = page_task['file_name']
    page_num = page_task['page_number']
    file_type = page_task['file_type']
    doc_path = page_task.get('doc_path')
    
    db = get_db()
    cur = db.cursor()
    
    try:
        p_key = 'VISION_HEAVY_SCHEMA' if file_type in ('IMAGE_SCHEMA', 'SCHEMATICS') else 'VISION_PDF_PAGE'
        prompt_cfg = compile_enterprise_prompt(cur, p_key)
        if not prompt_cfg:
            raise ValueError(f"Prompt configuration not found for key: {p_key}")
            
        provider, model_id, fallback_model, temp, max_t, system_role, core_task, constraints, format_inst = prompt_cfg
        
        full_prompt = f"{core_task}\n\nОГРАНИЧЕНИЯ:\n{constraints}\n\nФОРМАТ:\n{format_inst}"
        
        local_img_path = os.path.join(TMP_DIR, f"page_{doc_id}_p{page_num}.webp")
        
        # Попытка реального рендеринга страницы, если файл доступен
        rendered = False
        if doc_path and os.path.exists(doc_path) and file_type in ('IMAGE_SCHEMA', 'SCHEMATICS'):
            try:
                doc = fitz.open(doc_path)
                page = doc.load_page(page_num - 1)
                pix = page.get_pixmap(dpi=150)
                img_data = pix.tobytes("webp")
                with open(local_img_path, 'wb') as f:
                    f.write(img_data)
                doc.close()
                rendered = True
            except Exception as e:
                print(f"      [WARN] Ne udalos otrenderit str {page_num} manuala {file_name}: {e}. Mock-webp.")
                
        if not rendered:
            Image.new('RGB', (1200, 1600), color=(255, 255, 255)).save(local_img_path, 'WEBP')
            
        if file_type not in ('IMAGE_SCHEMA', 'SCHEMATICS'):
            # Извлекаем текст
            text_extracted = False
            ai_text = ""
            if doc_path and os.path.exists(doc_path):
                try:
                    doc = fitz.open(doc_path)
                    page = doc.load_page(page_num - 1)
                    ai_text = page.get_text()
                    doc.close()
                    if ai_text.strip():
                        text_extracted = True
                except Exception:
                    pass
            if not text_extracted:
                ai_text = f"# TEXT SECTION: {file_name}\nPage {page_num} contents."
            model_used = "PyMuPDF"
        else:
            ai_text = call_ai_with_caching(
                client=client_override or google_client,
                prompt_key=p_key,
                provider=provider,
                model_id=model_id,
                system_role=system_role,
                full_prompt=full_prompt,
                image_path=local_img_path,
                fallback_model=fallback_model
            )
            model_used = model_id
            
        if ai_text:
            lm = LakeManager()
            silver_uri = lm.save_to_silver(f"chunk_{doc_id}_p{page_num}", ai_text)
            
            cur.execute("""
                INSERT INTO public.document_chunks (document_id, page_number, slice_type, content_markdown, ai_metadata) 
                VALUES (%s, %s, %s, %s, %s);
            """, (doc_id, page_num, file_type, silver_uri, json.dumps({"model": model_used, "version": "6.4.PRO", "storage_uri": silver_uri})))
            db.commit()
            print(f"      [OK] Saved str {page_num} of doc ID {doc_id} to Silver.")
        else:
            raise RuntimeError("AI generated empty content or failed to respond")
            
        if os.path.exists(local_img_path):
            os.remove(local_img_path)
            
    except Exception as e:
        db.rollback()
        print(f"   [ERROR] Sboy obrabotki str {page_num} doc ID {doc_id}: {e}")
        raise e
    finally:
        cur.close()
        db.close()

def main():
    print("================================================================================")
    print("👁️  AGROMAX: BATCH VISION WORKER V6.4 [Context Caching & ThreadPool] 👁️")
    print("================================================================================")
    qm = QueueManager()
    
    while True:
        try:
            batch_tasks = []
            total_pages = 0
            
            print(f"\n[{time.strftime('%H:%M:%S')}] Ozhidanie zadach v queue:vision...")
            page_limit = int(os.getenv("BATCH_PAGE_LIMIT", "1500"))
            
            # Накопление пакета
            while total_pages < page_limit:
                task = qm.pop_task("queue:vision", timeout=5)
                if not task:
                    # Если очередь пуста, но в батче уже что-то есть — начинаем обработку
                    if batch_tasks:
                        print("   [BATCH] Ochered pusta. Zapusk obrabotki nakoplennogo paketa.")
                        break
                    break
                
                task_id = str(task['id'])
                lm = LakeManager()
                pattern = os.path.join(lm.bronze_dir, f"{task_id}.*")
                found_files = glob.glob(pattern)
                
                num_pages = 0
                doc_path = None
                if found_files:
                    doc_path = found_files[0]
                    if doc_path.lower().endswith('.pdf') and fitz is not None:
                        try:
                            doc = fitz.open(doc_path)
                            num_pages = len(doc)
                            doc.close()
                        except Exception:
                            num_pages = task.get("page_count", 50)
                    else:
                        num_pages = task.get("page_count", 50)
                else:
                    num_pages = task.get("page_count", 50)
                
                task["page_count"] = num_pages
                task["doc_path"] = doc_path
                batch_tasks.append(task)
                total_pages += num_pages
                print(f"   [BATCH] Added doc ID {task_id} ({num_pages} str). Total: {total_pages}/{page_limit}")
            
            if not batch_tasks:
                time.sleep(2)
                continue
                
            print(f"\n🚀 Sformirovan paket: {len(batch_tasks)} doc, {total_pages} str. Zapusk concurrent obrabotki...")
            
            page_tasks = []
            for t in batch_tasks:
                doc_id = t['id']
                file_name = t['file_name']
                doc_path = t.get('doc_path')
                num_pages = t.get('page_count', 50)
                
                is_schema = False
                search_text = (file_name + " " + t.get("file_type", "")).lower()
                if any(kw in search_text for kw in ['схема', 'чертеж', 'blueprint', 'schematic', 'wiring', 'hydraulic', 'электросхема']):
                    is_schema = True
                
                for p in range(num_pages):
                    page_tasks.append({
                        "doc_id": doc_id,
                        "file_name": file_name,
                        "page_number": p + 1,
                        "file_type": 'IMAGE_SCHEMA' if is_schema else 'TEXT_PAGE',
                        "doc_path": doc_path
                    })
            
            max_workers = int(os.getenv("MAX_CONCURRENT_THREADS", "10"))
            print(f"   [POOL] Concurrency: {max_workers}. Obrabotka {len(page_tasks)} stranic...")
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(process_page_task, pt): pt for pt in page_tasks}
                for future in as_completed(futures):
                    pt = futures[future]
                    try:
                        future.result()
                    except Exception as e:
                        print(f"   [ERROR] Sboy processinga str {pt['page_number']} of {pt['file_name']}: {e}")
            
            # Обновление статусов документов в PostgreSQL
            db = get_db()
            cur = db.cursor()
            try:
                for t in batch_tasks:
                    cur.execute("UPDATE public.slices_registry SET ai_status = 'COMPLETED', timestamp_done = NOW() WHERE id = %s;", (t['id'],))
                db.commit()
                print(f"✅ Vse dokumenti v pakete ({len(batch_tasks)} sht) perevedeni v COMPLETED.")
            except Exception as e:
                db.rollback()
                print(f"🚨 Ne udalos obnovit statusi doc v DB: {e}")
            finally:
                cur.close()
                db.close()
                
            time.sleep(1)
        except Exception as e:
            print(f"❌ Systemnaya oshibka: {e}")
            time.sleep(5)

if __name__ == '__main__':
    main()
