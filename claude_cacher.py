import anthropic
import os

# Инициализация клиента (API ключ должен быть в переменных окружения ANTHROPIC_API_KEY)
client = anthropic.Anthropic()

def send_with_cache(prompt_text, user_query):
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt_text,
                        "cache_control": {"type": "ephemeral"} # Включение кэширования
                    },
                    {
                        "type": "text",
                        "text": user_query
                    }
                ]
            }
        ]
    )
    return response.content[0].text

if __name__ == "__main__":
    system_prompt = "ВСТАВЬТЕ_СЮДА_ВАШ_БОЛЬШОЙ_ПРОМПТ_AGROMAX"
    query = "Проанализируй чертеж ступицы РСМ 2400"
    
    result = send_with_cache(system_prompt, query)
    print(result)
