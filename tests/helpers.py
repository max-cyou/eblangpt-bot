import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import config
from database import initialize_database
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message


def make_message(text='привет', chat_id=1, chat_type='private', **extra):
    data = {
        'message_id': 1, 'date': 0,
        'chat': {'id': chat_id, 'type': chat_type, 'title': 'Group' if chat_type != 'private' else None},
        'from': {'id': 42, 'is_bot': False, 'first_name': 'Offline', 'username': 'offline'},
        'text': text, **extra,
    }
    if text and text.startswith('/'):
        data['entities'] = [{'type': 'bot_command', 'offset': 0, 'length': len(text.split()[0])}]
    return Message.de_json(data)


class Response:
    def __init__(self, result=None, lines=None, status=200):
        self.result = result if result is not None else {'choices': [{'message': {'content': 'offline answer'}}]}
        self.lines = lines
        self.status = status
        self.headers = {'Content-Type': 'text/event-stream' if lines is not None else 'application/json'}
        self.content = self

    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    def raise_for_status(self):
        import aiohttp
        if self.status >= 400:
            raise aiohttp.ClientResponseError(None, (), status=self.status)
    async def json(self): return self.result
    async def read(self): return b''
    def __aiter__(self):
        async def lines():
            for line in self.lines:
                yield line.encode()
        return lines()


class Session:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [Response()])

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(response, Exception):
            raise response
        return response


class BotTestMixin:
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.settings = patch.multiple(
            config, DATABASE_PATH=Path(self.directory.name) / 'state.sqlite3',
            GROUP_RANDOM_REPLY_MIN=100, GROUP_RANDOM_REPLY_MAX=100,
            START_IMAGE_PATH=config.PROJECT_ROOT / 'assets/eblan.png',
            GROUP_WELCOME_IMAGE_PATH=config.PROJECT_ROOT / 'assets/eblan-group.png',
        )
        self.settings.start()
        initialize_database(config.DATABASE_PATH)
        self.bot = AsyncTeleBot('123456:offline-token')
        self.bot.get_me = AsyncMock(return_value=SimpleNamespace(id=999, username='offlinebot'))
        self.bot.send_rich_message = AsyncMock(return_value=make_message('status'))
        self.bot.send_message = AsyncMock(return_value=make_message('status'))
        self.bot.send_rich_message_draft = AsyncMock(return_value=True)
        self.bot.edit_message_text = AsyncMock(return_value=True)
        self.bot.send_chat_action = AsyncMock(return_value=True)
        self.bot.send_photo = AsyncMock(return_value=make_message('photo'))
        self.session = Session()

    def tearDown(self):
        self.settings.stop()
        self.directory.cleanup()
