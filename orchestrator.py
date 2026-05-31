import os
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

# Заставляем Python прочитать ваш .env файл
load_dotenv("/root/agromax_infinity/.env")

class AgromaxOrchestrator:
    def __init__(self, registry_path="/root/agromax_infinity/Registry.csv"):
        self.registry = pd.read_csv(registry_path)
        
        # Ключ теперь автоматически подтягивается из .env
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("Ключ OPENROUTER_API_KEY не найден в .env файле!")
            
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key
        )

    def get_model_config(self, prompt_key):
        row = self.registry[self.registry['prompt_key'] == prompt_key]
        if row.empty:
            raise ValueError(f"Ключ промпта {prompt_key} не найден в Registry.csv")
        return row.iloc[0]

    def call_model(self, prompt_key, user_prompt, system_role=None):
        config = self.get_model_config(prompt_key)
        model_id = config['model_id']
        
        messages = []
        if system_role:
            messages.append({"role": "system", "content": system_role})
        messages.append({"role": "user", "content": user_prompt})

        response = self.client.chat.completions.create(
            model=model_id,
            messages=messages,
            temperature=float(config['temperature']),
            extra_headers={
                "HTTP-Referer": "https://agromax.infinity",
                "X-Title": "Agromax Orchestrator"
            }
        )
        return response.choices[0].message.content
