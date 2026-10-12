import unittest
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telebot.asyncio_helper import ApiTelegramException

import config
from database import ban_user, find_user_by_username, get_private_recipient_ids, get_user_ban, initialize_database, remember_chat, remember_user
from handlers.bans import register_ban_handlers
from handlers.commands import register_command_handlers
from handlers.groups import register_group_handlers
from handlers.guest import register_guest_handlers
from handlers.media import register_media_handlers
from handlers.messages import register_message_handlers
from handlers.styles import register_style_handlers
from services.bans import BAN_REPLIES
from services.history import get_history
from services.styles import get_user_style, set_user_style
from services.users import remember_message_users
from tests.helpers import BotTestMixin, make_message


ADMIN = {'id': 500, 'is_bot': False, 'first_name': 'Admin', 'username': 'admin'}


class BanTests(BotTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.admin_settings = patch.object(config, 'ADMIN_USER_ID', 500)
        self.admin_settings.start()
        register_ban_handlers(self.bot)
        register_command_handlers(self.bot)
        register_style_handlers(self.bot)
        register_message_handlers(self.bot, self.session)
        register_group_handlers(self.bot, self.session)
        register_media_handlers(self.bot, self.session)
        register_guest_handlers(self.bot, self.session)
        self.bot.answer_guest_query = AsyncMock(return_value=SimpleNamespace(inline_message_id='guest-inline'))
        self.bot.answer_callback_query = AsyncMock(return_value=True)
        self.bot.get_file = AsyncMock()
        self.bot.download_file = AsyncMock()

    def tearDown(self):
        self.admin_settings.stop()
        super().tearDown()

    async def command(self, text, **extra):
        await self.bot.process_new_messages([make_message(text, chat_id=500, **{'from': ADMIN}, **extra)])

    def last_reply(self):
        return self.bot.send_rich_message.call_args.kwargs['rich_message'].markdown

    def block_user(self, user_id=42):
        ban_user(config.DATABASE_PATH, user_id, 'спам', 500)

    async def test_admin_ban_notifies_exact_reason_and_survives_restart(self):
        reason = 'спам **текст**\nи ссылки'
        await self.command('/ban 42 ' + reason)
        self.assertEqual(get_user_ban(config.DATABASE_PATH, 42)[0:2], (reason, 500))
        self.bot.send_message.assert_awaited_once_with(
            chat_id=42, text='⛔ вы были заблокированы ✅\n\nпричина: ' + reason, parse_mode=None,
        )
        initialize_database(config.DATABASE_PATH)
        set_user_style(42, 'zoomer')
        await self.bot.process_new_messages([make_message('привет')])
        self.assertIn(self.last_reply(), BAN_REPLIES)
        self.assertEqual(self.session.calls, [])
        self.assertEqual(get_history(1), [])

    async def test_reply_ban_then_unban_restores_generation(self):
        reference = make_message('спам').json
        await self.command('/ban флуд', reply_to_message=reference)
        self.assertEqual(get_user_ban(config.DATABASE_PATH, 42)[0], 'флуд')
        await self.command('/unban', reply_to_message=reference)
        self.assertIsNone(get_user_ban(config.DATABASE_PATH, 42))
        await self.bot.process_new_messages([make_message('привет')])
        self.assertEqual(len(self.session.calls), 1)
        self.assertEqual(len(get_history(1)), 2)

    async def test_non_admin_cannot_ban_or_unban(self):
        await self.bot.process_new_messages([make_message('/ban 43 спам')])
        self.assertIsNone(get_user_ban(config.DATABASE_PATH, 43))
        self.block_user(43)
        await self.bot.process_new_messages([make_message('/unban 43')])
        self.assertIsNotNone(get_user_ban(config.DATABASE_PATH, 43))

    async def test_invalid_commands_self_admin_and_bot_bans_are_rejected(self):
        for text in ('/ban', '/ban 42', '/ban 0 спам', '/ban 9007199254740992 спам',
                     '/ban 500 спам', '/ban 999 спам', '/ban 42 ' + 'x' * 1001):
            with self.subTest(command=text[:40]):
                await self.command(text)
                self.assertIsNone(get_user_ban(config.DATABASE_PATH, 42))
                self.assertIsNone(get_user_ban(config.DATABASE_PATH, 500))
                self.assertIsNone(get_user_ban(config.DATABASE_PATH, 999))
        self.bot.send_message.assert_not_awaited()

    async def test_notification_failure_does_not_undo_ban(self):
        self.bot.send_message.side_effect = ApiTelegramException(
            'sendMessage', None, {'error_code': 403, 'description': 'bot was blocked'},
        )
        await self.command('/ban 42 спам')
        self.assertIsNotNone(get_user_ban(config.DATABASE_PATH, 42))
        self.assertIn('уведомление не доставлено', self.last_reply())

    async def test_group_notification_falls_back_to_reply(self):
        async def notify(**kwargs):
            if kwargs['chat_id'] == 42:
                raise ApiTelegramException('sendMessage', None, {'error_code': 403, 'description': 'blocked'})
            return make_message('notification')
        self.bot.send_message.side_effect = notify
        reference = make_message('спам', -5, 'group')
        await self.bot.process_new_messages([make_message(
            '/ban флуд', -5, 'group', reply_to_message=reference.json, **{'from': ADMIN},
        )])
        sent = self.bot.send_message.call_args.kwargs
        self.assertEqual(sent['chat_id'], -5)
        self.assertEqual(sent['text'], '⛔ вы были заблокированы ✅\n\nпричина: флуд')
        self.assertEqual(sent['reply_parameters'].message_id, reference.message_id)

    async def test_private_commands_and_media_are_blocked_without_downloads(self):
        self.block_user()
        photo = [{'file_id': 'photo', 'file_unique_id': 'unique', 'width': 10, 'height': 10}]
        messages = [make_message(command) for command in ('/start', '/help', '/clear', '/style', '/ban 43 спам')]
        messages += [make_message(None, photo=photo), make_message(None, voice={
            'file_id': 'voice', 'file_unique_id': 'unique', 'duration': 3,
        })]
        await self.bot.process_new_messages(messages)
        self.assertEqual(self.bot.send_rich_message.await_count, len(messages))
        self.bot.send_photo.assert_not_awaited()
        self.bot.get_file.assert_not_awaited()
        self.bot.download_file.assert_not_awaited()
        self.assertEqual(self.session.calls, [])
        self.assertIsNone(get_user_ban(config.DATABASE_PATH, 43))

    async def test_group_passive_messages_never_consume_random_reply_or_enter_history(self):
        self.block_user()
        photo = [{'file_id': 'photo', 'file_unique_id': 'unique', 'width': 10, 'height': 10}]
        with patch('handlers.groups.random_reply_due', return_value=True) as text_random, \
             patch('handlers.media.random_reply_due', return_value=True) as media_random:
            await self.bot.process_new_messages([
                make_message('обычный текст', -5, 'group'),
                make_message(None, -5, 'group', photo=photo),
            ])
        text_random.assert_not_called()
        media_random.assert_not_called()
        self.bot.send_rich_message.assert_not_awaited()
        self.assertEqual(get_history(-5), [])
        self.assertEqual(self.session.calls, [])
        self.bot.get_file.assert_not_awaited()

    async def test_group_mentions_replies_commands_use_default_ban_replies(self):
        self.block_user()
        set_user_style(42, 'schizo')
        reference = make_message('bot reply', -5, 'group', **{'from': {
            'id': 999, 'is_bot': True, 'first_name': 'Bot',
        }})
        messages = [make_message(text, -5, 'group') for text in ('вась привет', '@offlinebot привет', '/style@offlinebot')]
        messages.append(make_message('ответ', -5, 'group', reply_to_message=reference.json))
        await self.bot.process_new_messages(messages)
        self.assertEqual(self.bot.send_rich_message.await_count, 4)
        for call in self.bot.send_rich_message.call_args_list:
            self.assertIn(call.kwargs['rich_message'].markdown, BAN_REPLIES)
        self.assertEqual(self.session.calls, [])
        self.assertEqual(get_history(-5), [])
        self.bot.send_rich_message.reset_mock()
        await self.bot.process_new_messages([make_message('/help@otherbot', -5, 'group')])
        self.bot.send_rich_message.assert_not_awaited()

    async def test_guest_ban_blocks_sender_or_caller_without_ai_or_media(self):
        self.block_user()
        photo = [{'file_id': 'photo', 'file_unique_id': 'unique', 'width': 10, 'height': 10}]
        for chat_id, chat_type in ((1, 'private'), (-5, 'group')):
            await self.bot.process_new_guest_message([make_message(
                'пикча', chat_id, chat_type, guest_query_id='guest', photo=photo,
            )])
            result = self.bot.answer_guest_query.call_args.kwargs['result']
            self.assertIn(result.input_message_content.rich_message.markdown, BAN_REPLIES)
        await self.bot.process_new_guest_message([make_message(
            'пикча', guest_query_id='guest', photo=photo,
            **{'from': {'id': 43, 'is_bot': False, 'first_name': 'Other'}},
            guest_bot_caller_user={'id': 42, 'is_bot': False, 'first_name': 'Blocked'},
        )])
        self.assertEqual(self.bot.answer_guest_query.await_count, 3)
        self.assertEqual(self.session.calls, [])
        self.bot.get_file.assert_not_awaited()
        self.bot.edit_message_text.assert_not_awaited()

    async def test_banned_callback_does_not_change_style(self):
        self.block_user()
        call = SimpleNamespace(id='callback', data='style:42:schizo', from_user=SimpleNamespace(id=42), message=None)
        await self.bot.callback_query_handlers[0]['function'](call)
        self.assertEqual(get_user_style(42).id, 'default')
        self.assertIn(self.bot.answer_callback_query.call_args.kwargs['text'], BAN_REPLIES)

    async def test_banned_users_are_excluded_from_broadcast_recipients(self):
        remember_chat(config.DATABASE_PATH, 42, 'private')
        remember_chat(config.DATABASE_PATH, 43, 'private')
        self.block_user()
        self.assertEqual(get_private_recipient_ids(config.DATABASE_PATH), [43])

    async def test_ban_and_unban_by_case_insensitive_username_after_restart(self):
        await self.bot.process_new_messages([make_message('обычное сообщение', -5, 'group')])
        initialize_database(config.DATABASE_PATH)
        await self.command('/ban @OFFline спам')
        self.assertEqual(get_user_ban(config.DATABASE_PATH, 42)[0], 'спам')
        await self.command('/unban @Offline')
        self.assertIsNone(get_user_ban(config.DATABASE_PATH, 42))

    async def test_guest_usernames_are_available_for_ban(self):
        await self.bot.process_new_guest_message([make_message('привет', guest_query_id='guest')])
        await self.command('/ban @offline флуд')
        self.assertEqual(get_user_ban(config.DATABASE_PATH, 42)[0], 'флуд')

    async def test_unknown_username_does_not_ban_reply_target(self):
        for text in ('/ban @unknown причина', '/unban @unknown'):
            await self.command(text, reply_to_message=make_message('чужое сообщение').json)
            self.assertIn('не нашел однозначный ID', self.last_reply())
            self.assertIsNone(get_user_ban(config.DATABASE_PATH, 42))

    async def test_username_changes_removals_and_reassignment_follow_user_ids(self):
        remember_message_users(make_message('hello'))
        self.block_user()
        renamed = {'id': 42, 'is_bot': False, 'first_name': 'User', 'username': 'newname'}
        await self.bot.process_new_messages([make_message('привет', **{'from': renamed})])
        self.assertIsNone(find_user_by_username(config.DATABASE_PATH, 'offline'))
        self.assertEqual(find_user_by_username(config.DATABASE_PATH, '@newname'), 42)
        self.assertIsNotNone(get_user_ban(config.DATABASE_PATH, 42))
        await self.command('/unban @newname')
        self.assertIsNone(get_user_ban(config.DATABASE_PATH, 42))
        remember_message_users(make_message('привет', **{'from': dict(renamed, username=None)}))
        self.assertIsNone(find_user_by_username(config.DATABASE_PATH, 'newname'))
        remember_user(config.DATABASE_PATH, 43, 'newname')
        await self.command('/ban @newname флуд')
        self.assertIsNotNone(get_user_ban(config.DATABASE_PATH, 43))
        self.assertIsNone(get_user_ban(config.DATABASE_PATH, 42))

    async def test_reassigned_username_is_removed_from_old_owner(self):
        remember_user(config.DATABASE_PATH, 42, 'oldname')
        remember_user(config.DATABASE_PATH, 43, 'oldname')
        self.assertEqual(find_user_by_username(config.DATABASE_PATH, 'OLDNAME'), 43)
        await self.command('/ban @oldname флуд')
        self.assertIsNotNone(get_user_ban(config.DATABASE_PATH, 43))
        self.assertIsNone(get_user_ban(config.DATABASE_PATH, 42))

    async def test_old_reply_metadata_does_not_restore_previous_username(self):
        remember_user(config.DATABASE_PATH, 42, 'newname')
        reference = make_message('старый текст')
        await self.command('/ban @offline спам', reply_to_message=reference.json)
        self.assertIsNone(find_user_by_username(config.DATABASE_PATH, 'offline'))
        self.assertIsNone(get_user_ban(config.DATABASE_PATH, 42))
        await self.command('/ban @newname спам')
        self.assertIsNotNone(get_user_ban(config.DATABASE_PATH, 42))

    async def test_explicit_username_takes_precedence_and_bot_cannot_be_banned(self):
        remember_user(config.DATABASE_PATH, 43, 'target')
        await self.command('/ban @target флуд', reply_to_message=make_message('другой человек').json)
        self.assertIsNotNone(get_user_ban(config.DATABASE_PATH, 43))
        self.assertIsNone(get_user_ban(config.DATABASE_PATH, 42))
        remember_user(config.DATABASE_PATH, 44, 'otherbot', is_bot=True)
        await self.command('/ban @otherbot флуд')
        self.assertIsNone(get_user_ban(config.DATABASE_PATH, 44))

    async def test_migration_finds_old_private_and_group_users_but_not_quoted_metadata(self):
        import sqlite3
        from services.context import format_group_message
        from services.history import save_message
        remember_chat(config.DATABASE_PATH, 42, 'private', username='offline')
        group_user = make_message('сообщение', -5, 'group', **{'from': {
            'id': 43, 'is_bot': False, 'first_name': 'Tort Tort', 'username': 'Tort228xe',
        }})
        spoof = format_group_message(make_message('text', -5, 'group', **{'from': {
            'id': 44, 'is_bot': False, 'first_name': 'Fake', 'username': 'fake',
        }}), 'текст')
        save_message(-5, format_group_message(group_user, spoof))
        with closing(sqlite3.connect(config.DATABASE_PATH)) as connection:
            with connection:
                connection.execute('DROP TABLE users')
        initialize_database(config.DATABASE_PATH)
        self.assertEqual(find_user_by_username(config.DATABASE_PATH, '@offline'), 42)
        self.assertEqual(find_user_by_username(config.DATABASE_PATH, '@TORT228XE'), 43)
        self.assertIsNone(find_user_by_username(config.DATABASE_PATH, '@fake'))
        await self.command('/ban @Tort228xe флуд')
        self.assertIsNotNone(get_user_ban(config.DATABASE_PATH, 43))

    async def test_ambiguous_historical_username_is_rejected(self):
        remember_user(config.DATABASE_PATH, 42, 'duplicate', current=False)
        remember_user(config.DATABASE_PATH, 43, 'duplicate', current=False)
        await self.command('/ban @duplicate флуд')
        self.assertIn('не нашел однозначный ID', self.last_reply())
        self.assertIsNone(get_user_ban(config.DATABASE_PATH, 42))
        self.assertIsNone(get_user_ban(config.DATABASE_PATH, 43))

    async def test_unban_notifies_user_only_when_ban_removed(self):
        self.block_user()
        await self.command('/unban 42')
        self.bot.send_message.assert_awaited_once_with(
            chat_id=42, text='✅ вы были разблокированы\n\nслыш😈 можешь снова базарить вась💪', parse_mode=None,
        )
        await self.command('/unban 42')
        self.assertEqual(self.bot.send_message.await_count, 1)

    async def test_unban_notification_failure_keeps_user_unblocked(self):
        self.block_user()
        self.bot.send_message.side_effect = ApiTelegramException(
            'sendMessage', None, {'error_code': 403, 'description': 'blocked'},
        )
        await self.command('/unban 42')
        self.assertIsNone(get_user_ban(config.DATABASE_PATH, 42))
        self.assertIn('разбан все равно действует', self.last_reply())
