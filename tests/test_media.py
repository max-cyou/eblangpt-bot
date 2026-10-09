import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import config
from handlers.media import register_media_handlers
from handlers.messages import register_message_handlers
from services.history import get_history
from services.media import download_attachment, read_text_document, recognize_image
from tests.helpers import BotTestMixin, Response, Session, make_message


class MediaTests(BotTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        register_message_handlers(self.bot, self.session)
        register_media_handlers(self.bot, self.session)
        self.bot.get_file = AsyncMock(return_value=SimpleNamespace(file_size=20, file_path='offline'))
        self.bot.download_file = AsyncMock(return_value='текст из файла'.encode('cp1251'))

    async def test_document_and_location(self):
        document = {'file_id': 'file', 'file_unique_id': 'unique', 'file_name': 'text.txt', 'mime_type': 'text/plain', 'file_size': 20}
        await self.bot.process_new_messages([make_message(None, document=document, caption='прочитай')])
        text = self.session.calls[-1][1]['json']['messages'][-1]['content']
        self.assertIn('текст из файла', text)
        self.assertIn('прочитай', text)
        await self.bot.process_new_messages([make_message(None, location={'latitude': 55.7, 'longitude': 37.6})])
        self.assertIn('55.7', self.session.calls[-1][1]['json']['messages'][-1]['content'])

    async def test_voice_to_text_and_passive_group_voice(self):
        voice = {'file_id': 'file', 'file_unique_id': 'unique', 'duration': 3, 'mime_type': 'audio/ogg'}
        with patch.object(config, 'GROQ_API_KEY', 'offline-key'):
            self.session.responses = [Response({'text': 'привет'}), Response()]
            await self.bot.process_new_messages([make_message(None, voice=voice)])
            self.assertIn('привет', self.session.calls[-1][1]['json']['messages'][-1]['content'])
            self.session.responses = [Response({'text': 'обычный войс'})]
            before = len(self.session.calls)
            await self.bot.process_new_messages([make_message(None, -10, 'group', voice=voice)])
            self.assertEqual(len(self.session.calls), before + 1)
            self.assertIn('обычный войс', get_history(-10)[0]['content'])
            self.session.responses = [Response({'text': 'вась объясни'}), Response()]
            await self.bot.process_new_messages([make_message(None, -10, 'group', voice=voice)])
            self.assertIn('вась объясни', self.session.calls[-1][1]['json']['messages'][-1]['content'])

    async def test_vision_fallback_and_reply_caption(self):
        photo = {'file_id': 'file', 'file_unique_id': 'unique', 'width': 10, 'height': 10, 'file_size': 20}
        description = 'На изображении находится большая красная машина'
        self.session.responses = [Response(status=429), Response({'choices': [{'message': {'content': description}}]}), Response()]
        reference = make_message(None, photo=[photo], caption='original caption').json
        with patch.multiple(config, OPENROUTER_API_KEY='offline-key', OPENROUTER_VISION_MODEL='first', OPENROUTER_VISION_FALLBACK_MODELS=('second',)):
            await self.bot.process_new_messages([make_message('что за машина', reply_to_message=reference)])
        text = self.session.calls[-1][1]['json']['messages'][-1]['content']
        self.assertIn(description, text)
        self.assertIn('original caption', text)
        self.assertIn('что за машина', text)
        self.assertEqual(len(self.session.calls), 3)

    async def test_download_errors_and_size_limits_return_fallback(self):
        document = {'file_id': 'file', 'file_unique_id': 'unique', 'file_name': 'text.txt', 'mime_type': 'text/plain', 'file_size': config.TEXT_FILE_MAX_BYTES + 1}
        await self.bot.process_new_messages([make_message(None, document=document)])
        self.bot.get_file.assert_not_awaited()
        self.assertEqual(get_history(1), [])
        self.assertIn('слишком большой', self.bot.send_rich_message.call_args.kwargs['rich_message'].markdown)
