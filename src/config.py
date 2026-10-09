import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()

AI_API_KEY = os.getenv('AI_API_KEY', '')
AI_API_URL = os.getenv('AI_API_URL', '')
AI_MODEL = os.getenv('AI_MODEL', '')

if not BOT_TOKEN.strip():
    raise ValueError("Error: Bot token not found.")
