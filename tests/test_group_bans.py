import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import config
from database import ban_group, ban_user, get_group_ban, initialize_database
from handlers.bans import register_ban_handlers
from handlers.commands import register_command_handlers
from handlers.events import register_event_handlers
from handlers.group_bans import register_group_ban_handlers
from handlers.groups import register_group_handlers
from handlers.guest import register_guest_handlers
from handlers.media import register_media_handlers
from handlers.messages import register_message_handlers
from handlers.styles import register_style_handlers
from services.history import get_history
from services.styles import get_user_style
from tests.helpers import BotTestMixin, Response, make_message


ADMIN = {'id': 500, 'is_bot': False, 'first_name': 'Admin'}


class GroupBanTests(BotTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.admin_settings = patch.object(config, 'ADMIN_USER_ID', 500)
        self.admin_settings.start()
        register_group_ban_handlers(self.bot)
        register_ban_handlers(self.bot)
        register_command_handlers(self.bot)
        register_style_handlers(self.bot)
        register_message_handlers(self.bot, self.session)
        register_group_handlers(self.bot, self.session)
        register_media_handlers(self.bot, self.session)
        register_guest_handlers(self.bot, self.session)
        register_event_handlers(self.bot)
        self.bot.answer_guest_query = AsyncMock(return_value=SimpleNamespace(inline_message_id='guest-inline'))
        self.bot.answer_callback_query = AsyncMock(return_value=True)
        self.bot.get_file = AsyncMock()
        self.bot.download_file = AsyncMock()

    def tearDown(self):
        self.admin_settings.stop()
        super().tearDown()

    async def command(self, text, chat_id=-5, chat_type='group'):
        await self.bot.process_new_messages([make_message(text, chat_id, chat_type, **{'from': ADMIN})])

    async def test_group_ban_survives_restart_and_can_be_removed_in_blocked_group(self):
        await self.command('/bangroup')
        self.assertEqual(get_group_ban(config.DATABASE_PATH, -5)[0], 500)
        self.assertIn('группа в чс', self.bot.send_message.call_args.kwargs['text'])
        initialize_database(config.DATABASE_PATH)
        await self.bot.process_new_messages([make_message('вась привет', -5, 'group')])
        self.assertEqual(self.session.calls, [])
        await self.command('/unbangroup')
        self.assertIsNone(get_group_ban(config.DATABASE_PATH, -5))
        await self.bot.process_new_messages([make_message('вась привет', -5, 'group')])
        self.assertEqual(len(self.session.calls), 1)

    async def test_only_bot_admin_can_ban_and_unban_groups(self):
        await self.bot.process_new_messages([make_message('/bangroup', -5, 'group')])
        self.assertIsNone(get_group_ban(config.DATABASE_PATH, -5))
        ban_group(config.DATABASE_PATH, -5, 500)
        await self.bot.process_new_messages([make_message('/unbangroup', -5, 'group')])
        self.assertIsNotNone(get_group_ban(config.DATABASE_PATH, -5))
        self.assertIn('только для админа', self.bot.send_message.call_args.kwargs['text'])

    async def test_private_commands_arguments_and_other_bot_suffix_do_not_change_bans(self):
        await self.command('/bangroup', 500, 'private')
        self.assertIsNone(get_group_ban(config.DATABASE_PATH, 500))
        for text in ('/bangroup -10', '/bangroup@otherbot'):
            await self.command(text)
            self.assertIsNone(get_group_ban(config.DATABASE_PATH, -5))
        await self.command('/bangroup@offlinebot')
        self.assertIsNotNone(get_group_ban(config.DATABASE_PATH, -5))
        await self.command('/unbangroup@otherbot')
        self.assertIsNotNone(get_group_ban(config.DATABASE_PATH, -5))
        await self.command('/unbangroup@OFFLINEBOT')
        self.assertIsNone(get_group_ban(config.DATABASE_PATH, -5))

    async def test_banned_group_ignores_text_commands_media_and_events_without_random_or_history(self):
        ban_group(config.DATABASE_PATH, -5, 500)
        ban_user(config.DATABASE_PATH, 42, 'спам', 500)
        photo = [{'file_id': 'photo', 'file_unique_id': 'unique', 'width': 10, 'height': 10}]
        messages = [make_message(text, -5, 'group') for text in ('вась привет', 'обычный текст', '/help', '/style', '/clear')]
        messages += [
            make_message(None, -5, 'group', photo=photo, caption='вась пикча'),
            make_message(None, -5, 'group', voice={'file_id': 'voice', 'file_unique_id': 'u', 'duration': 3}),
            make_message(None, -5, 'group', new_chat_members=[{'id': 43, 'is_bot': False, 'first_name': 'User'}]),
        ]
        with patch('handlers.groups.random_reply_due', return_value=True) as text_random, \
             patch('handlers.media.random_reply_due', return_value=True) as media_random:
            await self.bot.process_new_messages(messages)
        text_random.assert_not_called()
        media_random.assert_not_called()
        self.assertEqual(self.session.calls, [])
        self.assertEqual(get_history(-5), [])
        self.bot.get_file.assert_not_awaited()
        self.bot.send_message.assert_not_awaited()
        self.bot.send_rich_message.assert_not_awaited()
        self.bot.send_photo.assert_not_awaited()

    async def test_guest_group_blocked_but_other_groups_and_private_guest_work(self):
        ban_group(config.DATABASE_PATH, -5, 500)
        await self.bot.process_new_guest_message([make_message('привет', -5, 'group', guest_query_id='blocked')])
        self.bot.answer_guest_query.assert_not_awaited()
        self.assertEqual(self.session.calls, [])
        for chat_id, chat_type in ((-6, 'supergroup'), (1, 'private')):
            await self.bot.process_new_guest_message([make_message('привет', chat_id, chat_type, guest_query_id='allowed')])
        self.assertEqual(self.bot.answer_guest_query.await_count, 2)
        self.assertEqual(len(self.session.calls), 2)

    async def test_topic_ban_covers_entire_supergroup(self):
        message = make_message('/bangroup', -5, 'supergroup', message_thread_id=10, is_topic_message=True, **{'from': ADMIN})
        await self.bot.process_new_messages([message])
        await self.bot.process_new_messages([make_message('вась ответь', -5, 'supergroup', message_thread_id=20, is_topic_message=True)])
        self.assertEqual(self.session.calls, [])
        await self.command('/unbangroup', -5, 'supergroup')
        await self.bot.process_new_messages([make_message('вась ответь', -5, 'supergroup', message_thread_id=20, is_topic_message=True)])
        self.assertEqual(len(self.session.calls), 1)

    async def test_callback_from_old_style_menu_cannot_change_style_in_blocked_group(self):
        ban_group(config.DATABASE_PATH, -5, 500)
        call = SimpleNamespace(id='callback', data='style:42:schizo', from_user=SimpleNamespace(id=42), message=make_message('/style', -5, 'group'))
        await self.bot.callback_query_handlers[0]['function'](call)
        self.assertEqual(get_user_style(42).id, 'default')
        self.assertIn('группа в чс', self.bot.answer_callback_query.call_args.kwargs['text'])

    async def test_generation_started_before_group_ban_does_not_publish_answer(self):
        response = Response()
        async def reply_then_ban():
            ban_group(config.DATABASE_PATH, -5, 500)
            return {'choices': [{'message': {'content': 'must not be sent'}}]}
        response.json = reply_then_ban
        self.session.responses = [response]
        await self.bot.process_new_messages([make_message('вась вопрос', -5, 'group')])
        self.bot.edit_message_text.assert_not_awaited()
        self.assertEqual(get_history(-5), [])

    async def test_guest_admin_can_ban_and_unban_without_membership_or_ai(self):
        for text in ('@offlinebot /bangroup', '@offlinebot /unbangroup'):
            await self.bot.process_new_guest_message([make_message(text, -5, 'group', guest_query_id='moderation', **{'from': ADMIN})])
            answer = self.bot.answer_guest_query.call_args.kwargs['result'].input_message_content.rich_message.markdown
            if text.endswith('/bangroup'):
                self.assertIsNotNone(get_group_ban(config.DATABASE_PATH, -5))
                self.assertIn('группа в чс', answer)
                initialize_database(config.DATABASE_PATH)
            else:
                self.assertIsNone(get_group_ban(config.DATABASE_PATH, -5))
                self.assertIn('группа разбанена', answer)
        self.assertEqual(self.session.calls, [])
        self.bot.send_message.assert_not_awaited()
        self.bot.edit_message_text.assert_not_awaited()

    async def test_guest_non_admin_cannot_change_group_blacklist(self):
        await self.bot.process_new_guest_message([make_message('@offlinebot /bangroup', -5, 'group', guest_query_id='guest')])
        self.assertIsNone(get_group_ban(config.DATABASE_PATH, -5))
        ban_group(config.DATABASE_PATH, -5, 500)
        await self.bot.process_new_guest_message([make_message('@offlinebot /unbangroup', -5, 'group', guest_query_id='guest')])
        self.assertIsNotNone(get_group_ban(config.DATABASE_PATH, -5))
        answer = self.bot.answer_guest_query.call_args.kwargs['result'].input_message_content.rich_message.markdown
        self.assertIn('только для админа', answer)
        self.assertEqual(self.session.calls, [])

    async def test_guest_moderation_uses_actual_caller_instead_of_reference_author(self):
        await self.bot.process_new_guest_message([make_message(
            '@offlinebot /bangroup', -5, 'group', guest_query_id='guest',
            **{'from': ADMIN}, guest_bot_caller_user={'id': 42, 'is_bot': False, 'first_name': 'User'},
        )])
        self.assertIsNone(get_group_ban(config.DATABASE_PATH, -5))
        await self.bot.process_new_guest_message([make_message(
            '@offlinebot /bangroup', -5, 'group', guest_query_id='guest', guest_bot_caller_user=ADMIN,
        )])
        self.assertEqual(get_group_ban(config.DATABASE_PATH, -5)[0], 500)

    async def test_guest_group_commands_reject_private_chats_arguments_and_wrong_mentions(self):
        for text in ('@offlinebot /bangroup extra', '@otherbot /bangroup', '/bangroup@otherbot'):
            await self.bot.process_new_guest_message([make_message(text, -5, 'group', guest_query_id='guest', **{'from': ADMIN})])
            self.assertIsNone(get_group_ban(config.DATABASE_PATH, -5))
        await self.bot.process_new_guest_message([make_message('@offlinebot /bangroup', guest_query_id='private', **{'from': ADMIN})])
        self.assertIsNone(get_group_ban(config.DATABASE_PATH, 1))
        await self.bot.process_new_guest_message([make_message('/bangroup@OFFLINEBOT', -5, 'supergroup', guest_query_id='guest', **{'from': ADMIN})])
        self.assertIsNotNone(get_group_ban(config.DATABASE_PATH, -5))
        await self.bot.process_new_guest_message([make_message('/unbangroup', -5, 'supergroup', guest_query_id='guest', **{'from': ADMIN})])
        self.assertIsNone(get_group_ban(config.DATABASE_PATH, -5))
