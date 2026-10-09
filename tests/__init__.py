import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
os.environ.update(
    TELEGRAM_BOT_TOKEN='123456:offline-token',
    AI_API_KEY='offline-key',
    AI_API_URL='https://example.invalid/v1/chat/completions',
    AI_MODEL='offline-model',
)
