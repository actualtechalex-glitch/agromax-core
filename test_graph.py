import json
from orchestrator import AgromaxOrchestrator

orchestrator = AgromaxOrchestrator()

def run_graph_test():
    print("--- ЗАПУСК ВАЛИДАЦИИ (Стресс-тест GRAPH_BUILDER) ---")
    
    # Загружаем наш бриллиантовый промпт для графов
    with open("/root/agromax_infinity/prompts/graph_builder.md", "r", encoding="utf-8") as f:
        system_prompt = f.read()

    # Идеально чистые данные, которые мы получили от парсера страниц (Vision)
    extracted_context = """
    Узел: Гидронасос.
    Действие: Установка на монтажный фланец.
    Компонент: Болт крепления гидронасоса М16х1.5 (Артикул: RSM-100293).
    Инструмент: Динамометрический ключ.
    Параметр: Момент затяжки 120 Нм.
    Предупреждение: Перед установкой убедиться в отсутствии давления в гидравлической системе. Опасность выброса масла под высоким давлением.
    """

    print("Отправка чистого контекста в онтологический модуль (Gemini 3.1 Pro)...")
    
    try:
        response = orchestrator.call_model(
            prompt_key="GRAPH_BUILDER", 
            user_prompt=f"Сформируй триплеты для LightRAG на основе этих данных:\n\n{extracted_context}", 
            system_role=system_prompt
        )
        print("\n--- РЕЗУЛЬТАТ ПОСТРОЕНИЯ ГРАФА (JSON Триплеты) ---")
        print(response)
    except Exception as e:
        print(f"Ошибка вызова: {e}")

if __name__ == "__main__":
    run_graph_test()
