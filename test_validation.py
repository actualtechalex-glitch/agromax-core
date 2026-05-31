import json
from orchestrator import AgromaxOrchestrator

orchestrator = AgromaxOrchestrator()

def run_test():
    print("--- ЗАПУСК ВАЛИДАЦИИ (Стресс-тест парсера) ---")
    
    with open("/root/agromax_infinity/prompts/vision_pdf_page.md", "r", encoding="utf-8") as f:
        system_prompt = f.read()

    # Эмулируем текст, считанный с PDF страницы декабрьской инструкции
    mock_pdf_content = """
    Таблица 4.2. Моменты затяжки резьбовых соединений гидравлики.
    Болт крепления гидронасоса М16х1.5 (Артикул: RSM-100293) - 120 Нм.
    
    ВНИМАНИЕ! При установке гидронасоса убедитесь в отсутствии давления в системе (опасность выброса масла!). 
    
    Инструкция по монтажу (текст):
    Шаг 1. Установите гидронасос на фланец.
    Шаг 2. Затяните болты крепления гидронасоса (М16х1.5) с усилием 90 Нм.
    """

    print("Отправка запроса в OpenRouter (модель из Registry.csv)...")
    
    try:
        response = orchestrator.call_model(
            prompt_key="VISION_PDF_PAGE", 
            user_prompt=f"Проанализируй извлеченный текст страницы:\n\n{mock_pdf_content}", 
            system_role=system_prompt
        )
        print("\n--- РЕЗУЛЬТАТ АНАЛИЗА (JSON) ---")
        print(response)
    except Exception as e:
        print(f"Ошибка вызова: {e}")

if __name__ == "__main__":
    run_test()
