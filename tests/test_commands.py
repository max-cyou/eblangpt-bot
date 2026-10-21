import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from telebot import types

import config
from handlers.commands import register_command_handlers, register_command_menu, send_picture_or_text
from tests.helpers import BotTestMixin, make_message
from tests.test_admin_guest import telegram_error


class CommandTests(BotTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        register_command_handlers(self.bot)
        self.bot.set_my_commands = AsyncMock(return_value=True)

    async def test_welcome_text_retries_rate_limit_and_keeps_topic_and_buttons(self):
        path = Path(self.directory.name) / 'welcome.png'
        message = make_message('/start', -5, 'supergroup', message_thread_id=17)
        keyboard = types.InlineKeyboardMarkup()
        keyboard.row(types.InlineKeyboardButton('test', url='https://example.com'))
        delivered = make_message('welcome')
        for missing in (True, False):
            with self.subTest(missing_image=missing):
                if not missing:
                    path.write_bytes(b'offline image')
                    self.bot.send_photo.side_effect = telegram_error(400)
                self.bot.send_message.reset_mock()
                self.bot.send_message.side_effect = [telegram_error(429, parameters={'retry_after': 2}), delivered]
                with patch('services.telegram.asyncio.sleep', new_callable=AsyncMock) as sleep:
                    result = await send_picture_or_text(self.bot, message, path, 'welcome', keyboard)
                self.assertIs(result, delivered)
                self.assertEqual(self.bot.send_message.await_count, 2)
                sleep.assert_awaited_once_with(2)
                for call in self.bot.send_message.await_args_list:
                    self.assertEqual(call.kwargs, {
                        'chat_id': -5, 'text': 'welcome', 'reply_markup': keyboard, 'message_thread_id': 17,
                    })

    async def test_public_menu_and_private_admin_menu_are_separate(self):
        with patch.object(config, 'ADMIN_USER_ID', 500):
            await register_command_menu(self.bot)
        public, admin = self.bot.set_my_commands.await_args_list
        public_names = {'start', 'help', 'clear', 'style'}
        self.assertEqual({command.command for command in public.kwargs['commands']}, public_names)
        self.assertNotIn('scope', public.kwargs)
        self.assertIsInstance(admin.kwargs['scope'], types.BotCommandScopeChat)
        self.assertEqual(admin.kwargs['scope'].chat_id, 500)
        self.assertEqual({command.command for command in admin.kwargs['commands']}, public_names | {
            'stats', 'broadcast', 'ban', 'unban', 'banlist', 'bangroup', 'unbangroup',
        })

    async def test_username_only_admin_gets_private_menu_on_start(self):
        with patch.multiple(config, ADMIN_USER_ID=0, ADMIN_USERNAME='offline'):
            await register_command_menu(self.bot)
            self.bot.set_my_commands.assert_awaited_once()
            self.bot.set_my_commands.reset_mock()
            await self.bot.process_new_messages([make_message('/start', chat_id=42)])
        self.bot.set_my_commands.assert_awaited_once()
        scope = self.bot.set_my_commands.call_args.kwargs['scope']
        self.assertIsInstance(scope, types.BotCommandScopeChat)
        self.assertEqual(scope.chat_id, 42)

    async def test_start_does_not_publish_admin_commands_to_group_or_other_user(self):
        with patch.object(config, 'ADMIN_USER_ID', 42):
            await self.bot.process_new_messages([make_message('/start', -5, 'group')])
        with patch.object(config, 'ADMIN_USER_ID', 500):
            await self.bot.process_new_messages([make_message('/start')])
        self.bot.set_my_commands.assert_not_awaited()

    async def test_unknown_admin_chat_does_not_prevent_public_menu_setup(self):
        self.bot.set_my_commands.side_effect = [True, telegram_error(400, 'Bad Request: chat not found')]
        with patch.object(config, 'ADMIN_USER_ID', 500):
            await register_command_menu(self.bot)
        self.assertEqual(self.bot.set_my_commands.await_count, 2)
