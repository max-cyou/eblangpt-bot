import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import config
from services import media
from handlers.media import register_media_handlers
from handlers.messages import register_message_handlers
from services.history import get_history
from services.media import download_attachment, read_text_document, recognize_image, transcribe_audio
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
        self.session.responses = [Response(status=429), Response(status=429), Response({'choices': [{'message': {'content': description}}]}), Response()]
        reference = make_message(None, photo=[photo], caption='original caption').json
        with patch.multiple(config, OPENROUTER_API_KEY='offline-key', OPENROUTER_VISION_MODEL='first', OPENROUTER_VISION_FALLBACK_MODELS=('second',)):
            await self.bot.process_new_messages([make_message('что за машина', reply_to_message=reference)])
        text = self.session.calls[-1][1]['json']['messages'][-1]['content']
        self.assertIn(description, text)
        self.assertIn('original caption', text)
        self.assertIn('что за машина', text)
        self.assertEqual(len(self.session.calls), 4)
        self.assertEqual([call[1]['json']['model'] for call in self.session.calls[:-1]], ['first', 'first', 'second'])

    async def test_download_errors_and_size_limits_return_fallback(self):
        document = {'file_id': 'file', 'file_unique_id': 'unique', 'file_name': 'text.txt', 'mime_type': 'text/plain', 'file_size': config.TEXT_FILE_MAX_BYTES + 1}
        await self.bot.process_new_messages([make_message(None, document=document)])
        self.bot.get_file.assert_not_awaited()
        self.assertEqual(get_history(1), [])
        self.assertIn('слишком большой', self.bot.send_rich_message.call_args.kwargs['rich_message'].markdown)

    async def test_missing_vision_model_uses_backup(self):
        photo = SimpleNamespace(file_id='photo', file_size=20)
        description = 'На изображении находится большая красная машина'
        self.session.responses = [Response(status=404), Response(status=404), Response({'choices': [{'message': {'content': description}}]})]
        with patch.multiple(config, OPENROUTER_API_KEY='offline-key', OPENROUTER_VISION_MODEL='removed', OPENROUTER_VISION_FALLBACK_MODELS=('available',)):
            self.assertEqual(await recognize_image(self.bot, self.session, photo), description)
        self.assertEqual(len(self.session.calls), 3)
        self.assertEqual(self.session.calls[-1][1]['json']['model'], 'available')

    async def test_vision_retries_empty_response_before_next_model(self):
        description = 'На изображении находится большая красная машина'
        self.session.responses = [Response({'choices': []}), Response({'choices': [{'message': {'content': description}}]})]
        with patch.multiple(config, OPENROUTER_API_KEY='offline-key', OPENROUTER_VISION_MODEL='first', OPENROUTER_VISION_FALLBACK_MODELS=('second',)):
            self.assertEqual(await recognize_image(self.bot, self.session, SimpleNamespace(file_id='photo', file_size=20)), description)
        self.assertEqual([call[1]['json']['model'] for call in self.session.calls], ['first', 'first'])

    async def test_audio_retries_with_fresh_multipart_body(self):
        self.session.responses = [Response(status=503), Response({'text': 'распознанный текст'})]
        with patch.object(config, 'GROQ_API_KEY', 'offline-key'):
            text = await transcribe_audio(self.bot, self.session, SimpleNamespace(file_id='audio', file_size=20, mime_type='audio/ogg'))
        self.assertEqual(text, 'распознанный текст')
        self.assertEqual(len(self.session.calls), 2)
        self.assertIsNot(self.session.calls[0][1]['data'], self.session.calls[1][1]['data'])
        self.bot.download_file.assert_awaited_once()

    async def test_vision_retries_more_than_two_attempts_until_success(self):
        description = 'На изображении находится большая красная машина'
        self.session.responses = [Response(status=503) for _ in range(5)] + [Response({'choices': [{'message': {'content': description}}]})]
        with patch.multiple(config, OPENROUTER_API_KEY='offline-key', OPENROUTER_VISION_MODEL='first', OPENROUTER_VISION_FALLBACK_MODELS=('second',)):
            self.assertEqual(await recognize_image(self.bot, self.session, SimpleNamespace(file_id='photo', file_size=20)), description)
        self.assertEqual([call[1]['json']['model'] for call in self.session.calls], ['first', 'first', 'second', 'second', 'first', 'first'])
        self.bot.download_file.assert_awaited_once()

    async def test_vision_repeated_failures_stop_at_shared_deadline(self):
        self.session.responses = [Response(status=404)]
        with patch.object(config, 'OPENROUTER_API_KEY', 'offline-key'), patch.object(media, 'IMAGE_RECOGNITION_TIMEOUT', 0.02):
            with self.assertRaises(TimeoutError):
                await recognize_image(self.bot, self.session, SimpleNamespace(file_id='photo', file_size=20))
        self.assertGreater(len(self.session.calls), 2)
        attempts = len(self.session.calls)
        await asyncio.sleep(0)
        self.assertEqual(len(self.session.calls), attempts)

    async def test_vision_deadline_interrupts_stalled_request(self):
        async def stalled_json():
            await asyncio.sleep(1)

        response = Response()
        response.json = stalled_json
        self.session.responses = [response]
        started = asyncio.get_running_loop().time()
        with patch.object(config, 'OPENROUTER_API_KEY', 'offline-key'), patch.object(media, 'IMAGE_RECOGNITION_TIMEOUT', 0.02):
            with self.assertRaises(TimeoutError):
                await recognize_image(self.bot, self.session, SimpleNamespace(file_id='photo', file_size=20))
        self.assertLess(asyncio.get_running_loop().time() - started, 0.5)
        self.assertEqual(len(self.session.calls), 1)
