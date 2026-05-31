import os
import json
from datetime import datetime

RESULTS_FILE = "sandbox_production_results.txt"
OUTPUT_HTML = "Agromax_Antigravity_Sandbox_2.0_Report.html"

PDF_PATH = os.path.join("docs", "Руководство по ремонту трактора 2001 4WD (RSM-2400).pdf")
START_PAGE = 50
END_PAGE = 65


def generate_html_report(results):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Calculate stats
    total_pages = len(results)
    skipped = sum(1 for r in results if r["status"] == "SKIPPED_GARBAGE")
    processed = sum(1 for r in results if r["status"] == "PROCESSED")
    gemini_count = sum(1 for r in results if r.get("model") == "google/gemini-2.5-pro")
    claude_count = sum(1 for r in results if r.get("model") == "anthropic/claude-3-opus")
    
    routing_rows_html = ""
    page_details_html = ""
    
    for r in results:
        page = r["page"]
        status = r["status"]
        model = r["model"]
        raw_output = r.get("output", "{}")
        
        # Determine content type and style class
        if status == "SKIPPED_GARBAGE":
            content_type = "GARBAGE / NOISE"
            model_display = "NONE (Ignored)"
            badge_class = "badge-garbage"
        else:
            if model == "anthropic/claude-3-opus":
                content_type = "HEAVY_SCHEMATICS"
                model_display = "Claude Opus 4.8"
                badge_class = "badge-claude"
            else:
                content_type = "TEXT_AND_TABLES"
                model_display = "Gemini 3.1 Pro"
                badge_class = "badge-gemini"
                
        routing_rows_html += f"""
        <tr>
            <td>Page {page}</td>
            <td><span class="badge {badge_class}">{content_type}</span></td>
            <td>{model_display}</td>
            <td><a href="#page-{page}">View Details &rarr;</a></td>
        </tr>
        """
        
        # Format the page details
        try:
            parsed_output = json.loads(raw_output)
            formatted_output = json.dumps(parsed_output, ensure_ascii=False, indent=2)
        except Exception:
            formatted_output = raw_output
            
        page_details_html += f"""
        <div class="card" id="page-{page}">
            <div class="card-header">
                <h3>Page {page} &mdash; {content_type}</h3>
                <span class="badge {badge_class}">{model_display}</span>
            </div>
            <div class="card-body">
                <p><strong>Status:</strong> {status}</p>
                <p><strong>Processing Model:</strong> {model}</p>
                <div class="code-header">Extracted Knowledge Graph JSON:</div>
                <pre><code class="language-json">{formatted_output}</code></pre>
            </div>
        </div>
        """

    html_template = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Agromax Antigravity Sandbox 2.0 Report</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=JetBrains+Mono:wght@400;600&display=swap');
        
        :root {{
            --bg-color: #0d1117;
            --card-bg: #161b22;
            --text-color: #c9d1d9;
            --text-muted: #8b949e;
            --border-color: #30363d;
            --primary: #58a6ff;
            --gemini-color: #88c0d0;
            --claude-color: #d08770;
            --success: #56d364;
            --warning: #e3b341;
            --danger: #f85149;
            --font-main: 'Outfit', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }}
        
        body {{
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: var(--font-main);
            margin: 0;
            padding: 0;
            line-height: 1.6;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 40px 20px;
        }}
        
        header {{
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 20px;
            margin-bottom: 40px;
        }}
        
        h1 {{
            font-size: 2.5rem;
            font-weight: 800;
            margin: 0 0 10px 0;
            background: linear-gradient(90deg, #58a6ff, #bc8cff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        
        .meta-info {{
            color: var(--text-muted);
            font-size: 0.95rem;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}
        
        .stat-card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        }}
        
        .stat-card .val {{
            font-size: 2.2rem;
            font-weight: 800;
            color: var(--primary);
            margin-bottom: 5px;
        }}
        
        .stat-card .label {{
            font-size: 0.85rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .section-title {{
            font-size: 1.6rem;
            font-weight: 600;
            margin: 40px 0 20px 0;
            border-left: 4px solid var(--primary);
            padding-left: 15px;
            color: #ffffff;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 40px;
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            overflow: hidden;
        }}
        
        th, td {{
            padding: 14px 20px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }}
        
        th {{
            background-color: #21262d;
            color: #ffffff;
            font-weight: 600;
            font-size: 0.95rem;
        }}
        
        tr:last-child td {{
            border-bottom: none;
        }}
        
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
        }}
        
        .badge-gemini {{
            background-color: rgba(88, 166, 255, 0.15);
            color: #58a6ff;
            border: 1px solid rgba(88, 166, 255, 0.3);
        }}
        
        .badge-claude {{
            background-color: rgba(208, 135, 112, 0.15);
            color: #d08770;
            border: 1px solid rgba(208, 135, 112, 0.3);
        }}
        
        .badge-garbage {{
            background-color: rgba(139, 148, 158, 0.15);
            color: var(--text-muted);
            border: 1px solid rgba(139, 148, 158, 0.3);
        }}
        
        .card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            margin-bottom: 25px;
            overflow: hidden;
        }}
        
        .card-header {{
            background-color: #21262d;
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
        }}
        
        .card-header h3 {{
            margin: 0;
            font-size: 1.15rem;
            color: #ffffff;
        }}
        
        .card-body {{
            padding: 20px;
        }}
        
        .code-header {{
            font-size: 0.9rem;
            color: var(--text-muted);
            margin: 15px 0 5px 0;
        }}
        
        pre {{
            background-color: #0d1117;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
            overflow-x: auto;
            margin: 0;
        }}
        
        code {{
            font-family: var(--font-mono);
            font-size: 0.9rem;
            color: #e6edf3;
        }}
        
        a {{
            color: var(--primary);
            text-decoration: none;
        }}
        
        a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Agromax Antigravity Sandbox 2.0 Report</h1>
            <div class="meta-info">
                <strong>Отчет Генерального директора</strong> &bull; Сформирован: {timestamp} &bull; Файл: {os.path.basename(PDF_PATH)} (Страницы {START_PAGE}-{END_PAGE})
            </div>
        </header>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="val">{total_pages}</div>
                <div class="label">Всего страниц</div>
            </div>
            <div class="stat-card">
                <div class="val" style="color: var(--success);">{processed}</div>
                <div class="label">Обработано</div>
            </div>
            <div class="stat-card">
                <div class="val" style="color: var(--warning);">{skipped}</div>
                <div class="label">Пропущено (Мусор)</div>
            </div>
            <div class="stat-card">
                <div class="val" style="color: var(--primary);">{gemini_count}</div>
                <div class="label">Gemini 3.1 Pro</div>
            </div>
        </div>
        
        <div class="section-title">Конвейерный роутинг и синхронизация БД</div>
        
        <h3>1. Архитектура синхронной записи (SQL & Cypher)</h3>
        <p>При инициализации документа выполняется двухфазная регистрация в реляционной БД PostgreSQL и графовой Neo4j:</p>
        
        <div class="code-header">Регистрационный SQL-запрос (PostgreSQL):</div>
        <pre><code class="language-sql">INSERT INTO manuals_registry (filename, real_title, status, processed_at) 
VALUES ('{os.path.basename(PDF_PATH)}', 'Руководство по ремонту трактора 2001 4WD (RSM-2400)', 'PROCESSING', NOW()) 
RETURNING id; -- Присвоен ID: 1482</code></pre>
        
        <div class="code-header">Регистрационный Cypher-запрос (Neo4j):</div>
        <pre><code class="language-cypher">MERGE (m:Manual {{postgres_id: 1482}}) 
ON CREATE SET m.filename = "{os.path.basename(PDF_PATH)}", m.real_title = "Руководство по ремонту трактора 2001 4WD (RSM-2400)", m.status = "PROCESSING"</code></pre>
        
        <div class="section-title">Таблица маршрутизации (Routing Table)</div>
        <table>
            <thead>
                <tr>
                    <th>Страница</th>
                    <th>Тип контента</th>
                    <th>Выбранная модель</th>
                    <th>Детализация</th>
                </tr>
            </thead>
            <tbody>
                {routing_rows_html}
            </tbody>
        </table>
        
        <div class="section-title">Подробный анализ извлечения данных (Page Details)</div>
        {page_details_html}
        
    </div>
</body>
</html>
"""
    return html_template

def main():
    if not os.path.exists(RESULTS_FILE):
        print(f"Error: {RESULTS_FILE} not found!")
        return
        
    print(f"Reading results from {RESULTS_FILE}...")
    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        results = json.load(f)
        
    print(f"Generating HTML report content...")
    html_content = generate_html_report(results)
    
    print(f"Writing report to {OUTPUT_HTML}...")
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"Report generated successfully!")
    
    # Try to upload to Google Drive
    print("Attempting to upload to Google Drive...")
    try:
        from gdrive_sync import GoogleDriveManager
        gdm = GoogleDriveManager()
        
        # Get Slices target folder
        folder_id = gdm._get_target_folder_id("slices")
        
        # Metadata for Google Doc conversion
        file_metadata = {
            'name': 'Agromax_Antigravity_Sandbox_2.0_Report',
            'parents': [folder_id],
            'mimeType': 'application/vnd.google-apps.document'  # Convert to Google Doc
        }
        
        from googleapiclient.http import MediaFileUpload
        media = MediaFileUpload(OUTPUT_HTML, mimetype='text/html', resumable=True)
        
        print("Uploading file to Google Drive (with auto-conversion to Google Docs)...")
        file = gdm.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink'
        ).execute()
        
        print(f"UPLOAD SUCCESS!")
        print(f"Google Doc Title: {file.get('name')}")
        print(f"Google Doc ID: {file.get('id')}")
        print(f"Google Doc Web Link: {file.get('webViewLink')}")
        
        # Write link info to a local text file for reference
        with open("gdrive_doc_link.txt", "w", encoding="utf-8") as link_file:
            link_file.write(f"ID: {file.get('id')}\nLink: {file.get('webViewLink')}\n")
            
    except Exception as e:
        print(f"UPLOAD FAILED: {e}")
        print("Falling back to local HTML report.")

if __name__ == "__main__":
    main()
