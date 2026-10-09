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

OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '').strip()
OPENROUTER_CHAT_URL = os.getenv('OPENROUTER_CHAT_URL', 'https://openrouter.ai/api/v1/chat/completions').strip()
OPENROUTER_VISION_MODEL = os.getenv('OPENROUTER_VISION_MODEL', 'inclusionai/ling-3.0-flash-vl:free').strip()
OPENROUTER_VISION_FALLBACK_MODELS = tuple(
    item.strip() for item in os.getenv(
        'OPENROUTER_VISION_FALLBACK_MODELS',
        'google/gemma-4-26b-a4b-it:free,nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free',
    ).split(',') if item.strip()
)
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '').strip()
GROQ_TRANSCRIPT_URL = os.getenv('GROQ_TRANSCRIPT_URL', 'https://api.groq.com/openai/v1/audio/transcriptions').strip()
GROQ_TRANSCRIPT_MODEL = os.getenv('GROQ_TRANSCRIPT_MODEL', 'whisper-large-v3-turbo').strip()
TEXT_FILE_MAX_BYTES = positive_int('TEXT_FILE_MAX_BYTES', 512 * 1024)
TEXT_FILE_MAX_CHARS = positive_int('TEXT_FILE_MAX_CHARS', 24000)
IMAGE_MAX_BYTES = positive_int('IMAGE_MAX_BYTES', 10 * 1024 * 1024)
AUDIO_MAX_BYTES = positive_int('AUDIO_MAX_BYTES', 20 * 1024 * 1024)

if not BOT_TOKEN.strip():
    raise ValueError("Error: Bot token not found.")
if any(not v.strip() for v in (AI_API_KEY, AI_API_URL, AI_MODEL)):
    raise ValueError('Error: AI settings are missing.')
