import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telebot.asyncio_helper import ApiTelegramException

import config
from database import get_private_recipient_ids, get_statistics, remember_chat
from handlers.admin import register_admin_handlers
from handlers.commands import register_command_handlers
from handlers.events import register_event_handlers
from handlers.guest import register_guest_handlers
from services.history import get_history
from tests.helpers import BotTestMixin, Response, make_message


def telegram_error(code, description='offline error', **extra):
    return ApiTelegramException('offline', None, {'error_code': code, 'description': description, **extra})


class AdminGuestTests(BotTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        register_command_handlers(self.bot)
        register_admin_handlers(self.bot)
        register_event_handlers(self.bot)
        register_guest_handlers(self.bot, self.session)
        self.bot.answer_guest_query = AsyncMock(return_value=SimpleNamespace(inline_message_id='guest-inline'))
        self.bot.copy_message = AsyncMock(return_value=True)

    async def test_admin_restrictions_and_id_precedence(self):
        with patch.multiple(config, ADMIN_USER_ID=500, ADMIN_USERNAME='offline'):
            await self.bot.process_new_messages([make_message('/stats')])
            self.assertIn('тебе нельзя', self.bot.send_rich_message.call_args.kwargs['rich_message'].markdown)
            await self.bot.process_new_messages([make_message('/broadcast forbidden')])
            self.assertEqual(get_statistics(config.DATABASE_PATH).get('broadcasts', 0), 0)
        with patch.object(config, 'ADMIN_USER_ID', 42):
            await self.bot.process_new_messages([make_message('/stats')])
            self.assertIn('статистика', self.bot.send_rich_message.call_args.kwargs['rich_message'].markdown)

    async def test_broadcast_blocked_recipient_and_retry(self):
        remember_chat(config.DATABASE_PATH, 500, 'private')
        remember_chat(config.DATABASE_PATH, 501, 'private')
        blocked = set()
        async def send(**kwargs):
            if kwargs['chat_id'] == 501:
                raise telegram_error(403)
            if kwargs['chat_id'] == 500 and not blocked:
                blocked.add(500)
                raise telegram_error(429, parameters={'retry_after': 0})
            return make_message('sent')
        self.bot.send_rich_message.side_effect = send
        with patch.object(config, 'ADMIN_USER_ID', 42), patch('handlers.admin.asyncio.sleep', new_callable=AsyncMock):
            await self.bot.process_new_messages([make_message('/broadcast first\nsecond')])
        stats = get_statistics(config.DATABASE_PATH)
        self.assertEqual(stats['broadcast_deliveries'], 2)
        self.assertEqual(stats['broadcasts'], 1)
        self.assertNotIn(501, get_private_recipient_ids(config.DATABASE_PATH))
        self.assertEqual(self.bot.send_rich_message.call_args.kwargs['rich_message'].markdown, 'first\nsecond')

    async def test_broadcast_copies_reply(self):
        with patch.object(config, 'ADMIN_USER_ID', 42), patch('handlers.admin.asyncio.sleep', new_callable=AsyncMock):
            await self.bot.process_new_messages([make_message('/broadcast', reply_to_message=make_message('original').json)])
        self.bot.copy_message.assert_awaited_once()

    async def test_start_and_group_events(self):
        await self.bot.process_new_messages([make_message('/start')])
        self.bot.send_photo.assert_awaited_once()
        await self.bot.process_new_messages([make_message(None, -5, 'group', new_chat_members=[{'id': 999, 'is_bot': True, 'first_name': 'Bot'}])])
        self.assertTrue(get_history(-5))
        await self.bot.process_new_messages([make_message(None, -5, 'group', left_chat_member={'id': 40, 'is_bot': False, 'first_name': 'Leaving'})])
        self.assertIn('пошел', self.bot.send_rich_message.call_args.kwargs['rich_message'].markdown)

    async def test_guest_text_quote_and_statelessness(self):
        message = make_message('@offlinebot поясни', guest_query_id='guest',
                               reference_messages=[make_message('reference text').json],
                               quote={'text': 'quoted text', 'position': 0})
        await self.bot.process_new_guest_message([message])
        text = self.session.calls[-1][1]['json']['messages'][-1]['content']
        self.assertIn('reference text', text)
        self.assertIn('quoted text', text)
        self.assertNotIn('@offlinebot', text)
        self.assertEqual(get_history(1), [])
        self.assertEqual(get_statistics(config.DATABASE_PATH)['guest_requests'], 1)
        self.assertEqual(self.bot.edit_message_text.call_args.kwargs['inline_message_id'], 'guest-inline')

    async def test_guest_image_keeps_reference_text(self):
        photo = {'file_id': 'file', 'file_unique_id': 'unique', 'width': 10, 'height': 10}
        reference = make_message(None, photo=[photo], caption='important reference').json
        self.bot.get_file = AsyncMock(return_value=SimpleNamespace(file_size=5, file_path='offline'))
        self.bot.download_file = AsyncMock(return_value=b'image')
        self.session.responses = [Response({'choices': [{'message': {'content': 'На фото находится большая красная машина'}}]}), Response()]
        with patch.object(config, 'OPENROUTER_API_KEY', 'offline-key'):
            await self.bot.process_new_guest_message([make_message('что здесь', guest_query_id='guest', reference_messages=[reference])])
        text = self.session.calls[-1][1]['json']['messages'][-1]['content']
        self.assertIn('important reference', text)
        self.assertIn('красная машина', text)
        self.assertIn('что здесь', text)
