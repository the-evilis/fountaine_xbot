# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

from openai import OpenAI
from dotenv import load_dotenv
import os

# Загружаем ключ из .env файла
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Тестовый запрос
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {
            "role": "system",
            "content": "Ты помощник школы английского Fountaine English в Бишкеке. Отвечай кратко и по делу на русском языке."
        },
        {
            "role": "user", 
            "content": "Сколько стоят уроки английского?"
        }
    ],
    max_tokens=200
)

print(response.choices[0].message.content)