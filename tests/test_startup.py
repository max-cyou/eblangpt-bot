import unittest
from unittest.mock import AsyncMock, patch

import main
import config
from middlewares.admin import AdminMiddleware
from tests.helpers import BotTestMixin


class StartupTests(BotTestMixin, unittest.IsolatedAsyncioTestCase):
    async def test_registers_all_handlers_and_closes_sessions(self):
        self.bot.set_my_commands = AsyncMock(return_value=True)
        self.bot.infinity_polling = AsyncMock(return_value=None)
        self.bot.close_session = AsyncMock()
        with patch.object(main, 'AsyncTeleBot', return_value=self.bot), patch.object(config, 'ADMIN_USER_ID', 500):
            await main.main()
        self.assertEqual(len(self.bot.message_handlers), 20)
        self.assertEqual(len(self.bot.callback_query_handlers), 1)
        self.assertEqual(len(self.bot.guest_message_handlers), 1)
        self.assertEqual(len(self.bot.my_chat_member_handlers), 1)
        self.assertEqual(len(self.bot.middlewares), 1)
        self.assertIsInstance(self.bot.middlewares[0], AdminMiddleware)
        self.assertEqual(self.bot.set_my_commands.await_count, 2)
        self.assertEqual(self.bot.set_my_commands.call_args.kwargs['scope'].chat_id, 500)
        self.bot.close_session.assert_awaited_once()
        self.bot.infinity_polling.assert_awaited_once_with(allowed_updates=['message', 'guest_message', 'my_chat_member', 'callback_query'])

    async def test_closes_bot_if_startup_fails(self):
        self.bot.set_my_commands = AsyncMock(side_effect=RuntimeError('offline startup failure'))
        self.bot.close_session = AsyncMock()
        with patch.object(main, 'AsyncTeleBot', return_value=self.bot):
            with self.assertRaises(RuntimeError):
                await main.main()
        self.bot.close_session.assert_awaited_once()
