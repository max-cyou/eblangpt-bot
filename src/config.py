import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / '.env')

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()

AI_API_KEY = os.getenv('AI_API_KEY', '').strip()
AI_API_URL = os.getenv('AI_API_URL', '').strip()
AI_MODEL = os.getenv('AI_MODEL', '').strip()


def positive_int(name, default):
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f'{name} must be positive')
    return value


DATABASE_PATH = Path(os.getenv('DATABASE_PATH', 'data/eblangpt.sqlite3'))
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = PROJECT_ROOT / DATABASE_PATH
HISTORY_LIMIT = positive_int('HISTORY_LIMIT', 30)
CONTEXT_CHAR_LIMIT = positive_int('CONTEXT_CHAR_LIMIT', 8000)
AI_MAX_TOKENS = positive_int('AI_MAX_TOKENS', 600)
MAX_CONCURRENT_REQUESTS = positive_int('MAX_CONCURRENT_REQUESTS', 8)
GROUP_RANDOM_REPLY_MIN = positive_int('GROUP_RANDOM_REPLY_MIN', 10)
GROUP_RANDOM_REPLY_MAX = positive_int('GROUP_RANDOM_REPLY_MAX', 20)
if GROUP_RANDOM_REPLY_MIN > GROUP_RANDOM_REPLY_MAX:
    raise ValueError('GROUP_RANDOM_REPLY_MIN must not exceed GROUP_RANDOM_REPLY_MAX')

if not BOT_TOKEN.strip():
    raise ValueError("Error: Bot token not found.")
if any(not v.strip() for v in (AI_API_KEY, AI_API_URL, AI_MODEL)):
    raise ValueError('Error: AI settings are missing.')
