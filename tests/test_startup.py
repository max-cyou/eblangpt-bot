import unittest
from unittest.mock import AsyncMock, patch

import main
from tests.helpers import BotTestMixin


class StartupTests(BotTestMixin, unittest.IsolatedAsyncioTestCase):
    async def test_registers_all_handlers_and_closes_sessions(self):
        self.bot.set_my_commands = AsyncMock(return_value=True)
        self.bot.infinity_polling = AsyncMock(return_value=None)
        self.bot.close_session = AsyncMock()
        with patch.object(main, 'AsyncTeleBot', return_value=self.bot):
            await main.main()
        self.assertEqual(len(self.bot.message_handlers), 12)
        self.assertEqual(len(self.bot.callback_query_handlers), 1)
        self.assertEqual(len(self.bot.guest_message_handlers), 1)
        self.assertEqual(len(self.bot.my_chat_member_handlers), 1)
        self.bot.set_my_commands.assert_awaited_once()
        self.bot.close_session.assert_awaited_once()
        self.bot.infinity_polling.assert_awaited_once_with(allowed_updates=['message', 'guest_message', 'my_chat_member', 'callback_query'])

    async def test_closes_bot_if_startup_fails(self):
        self.bot.set_my_commands = AsyncMock(side_effect=RuntimeError('offline startup failure'))
        self.bot.close_session = AsyncMock()
        with patch.object(main, 'AsyncTeleBot', return_value=self.bot):
            with self.assertRaises(RuntimeError):
                await main.main()
        self.bot.close_session.assert_awaited_once()
