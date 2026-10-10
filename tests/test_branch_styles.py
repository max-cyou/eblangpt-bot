import base64
import struct
import unittest
from itertools import count
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import config
from database import initialize_database
from fallbacks.schizo import FALLBACKS
from handlers.groups import register_group_handlers
from handlers.guest import register_guest_handlers
from handlers.media import register_media_handlers
from handlers.messages import register_message_handlers
from services.branches import guest_reply_message_id
from services.styles import get_message_style, set_user_style
from styles import get_style
from tests.helpers import BotTestMixin, make_message


def user(user_id, bot=False):
    return {'id': user_id, 'is_bot': bot, 'first_name': 'User'}


def inline_id(message_id, boxed=False):
    data = struct.pack('<iqiq', 2, -10, message_id, 123)
    if boxed:
        data = struct.pack('<I', 0xB6D915D7) + data
    return base64.urlsafe_b64encode(data).decode().rstrip('=')


class BranchStyleTests(BotTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        register_message_handlers(self.bot, self.session)
        register_group_handlers(self.bot, self.session)
        register_media_handlers(self.bot, self.session)
        register_guest_handlers(self.bot, self.session)
        set_user_style(42, 'schizo')
        self.sent = []

        async def send(**kwargs):
            result = make_message('bot answer', kwargs['chat_id'], 'group' if kwargs['chat_id'] < 0 else 'private', **{'from': user(999, True)})
            self.sent.append(result)
            return result

        self.bot.send_rich_message.side_effect = send
        ids = count(100000)
        self.bot.answer_guest_query = AsyncMock(side_effect=lambda **kwargs: SimpleNamespace(inline_message_id=inline_id(next(ids), boxed=True)))

    def assert_last_prompt(self, style_id):
        self.assertEqual(self.session.calls[-1][1]['json']['messages'][0]['content'], get_style(style_id).system_prompt)

    async def test_group_passive_root_and_replies_keep_initial_style_after_restart(self):
        root = make_message('начало ветки', -10, 'group')
        await self.bot.process_new_messages([root])
        self.assertEqual(len(self.session.calls), 0)
        set_user_style(42, 'default')
        initialize_database(config.DATABASE_PATH)
        reply = make_message('вась ответь', -10, 'group', reply_to_message=root.json, **{'from': user(43)})
        await self.bot.process_new_messages([reply])
        self.assert_last_prompt('schizo')
        followup = make_message('продолжи', -10, 'group', reply_to_message=self.sent[-1].json, **{'from': user(44)})
        await self.bot.process_new_messages([followup])
        self.assert_last_prompt('schizo')
        await self.bot.process_new_messages([make_message('вась новая ветка', -10, 'group', **{'from': user(43)})])
        self.assert_last_prompt('default')

    async def test_private_reply_to_bot_keeps_pinned_style(self):
        await self.bot.process_new_messages([make_message('начало')])
        response = self.sent[-1]
        set_user_style(42, 'default')
        await self.bot.process_new_messages([make_message('продолжи', reply_to_message=response.json)])
        self.assert_last_prompt('schizo')
        await self.bot.process_new_messages([make_message('отдельный запрос')])
        self.assert_last_prompt('default')

    async def test_unseen_reply_root_uses_original_author(self):
        root = make_message('начало', -10, 'group')
        await self.bot.process_new_messages([make_message('вась ответь', -10, 'group', reply_to_message=root.json, **{'from': user(43)})])
        self.assert_last_prompt('schizo')

    async def test_topic_style_is_shared_and_topics_are_isolated(self):
        await self.bot.process_new_messages([make_message('вась начало', -10, 'supergroup', message_thread_id=90000, is_topic_message=True)])
        await self.bot.process_new_messages([make_message('вась продолжи', -10, 'supergroup', message_thread_id=90000, is_topic_message=True, **{'from': user(43)})])
        self.assert_last_prompt('schizo')
        await self.bot.process_new_messages([make_message('вась другое', -10, 'supergroup', message_thread_id=90001, is_topic_message=True, **{'from': user(43)})])
        self.assert_last_prompt('default')

    async def test_attachment_failure_uses_branch_style(self):
        root = make_message('начало', -10, 'group')
        await self.bot.process_new_messages([root])
        photo = [{'file_id': 'photo', 'file_unique_id': 'unique', 'width': 10, 'height': 10}]
        message = make_message(None, -10, 'group', photo=photo, caption='вась посмотри', reply_to_message=root.json, **{'from': user(43)})
        with patch.object(config, 'OPENROUTER_API_KEY', ''):
            await self.bot.process_new_messages([message])
        self.assertEqual(self.bot.edit_message_text.call_args.kwargs['rich_message'].markdown, FALLBACKS['vision_not_configured'])

    async def test_guest_replies_by_multiple_people_inherit_root_style(self):
        root = make_message('начало', -10, 'group', guest_query_id='first')
        await self.bot.process_new_guest_message([root])
        set_user_style(42, 'default')
        initialize_database(config.DATABASE_PATH)
        previous = make_message('bot answer', -10, 'group', message_id=100000, guest_bot_caller_user=user(42), **{'from': user(999, True)})
        await self.bot.process_new_guest_message([make_message('продолжи', -10, 'group', guest_query_id='second', reference_messages=[previous.json], **{'from': user(43)})])
        self.assert_last_prompt('schizo')
        previous = make_message('bot answer', -10, 'group', message_id=100001, guest_bot_caller_user=user(43), **{'from': user(999, True)})
        await self.bot.process_new_guest_message([make_message('еще', -10, 'group', guest_query_id='third', reply_to_message=previous.json, **{'from': user(44)})])
        self.assert_last_prompt('schizo')
        await self.bot.process_new_guest_message([make_message('новая ветка', -10, 'group', guest_query_id='new', **{'from': user(43)})])
        self.assert_last_prompt('default')

    async def test_guest_private_participants_share_branch_without_leaking_to_bot_chat(self):
        await self.bot.process_new_guest_message([make_message('начало', 43, 'private', guest_query_id='first')])
        previous = make_message('offline answer', 43, 'private', message_id=200000, guest_bot_caller_user=user(42), **{'from': user(999, True)})
        set_user_style(42, 'default')
        await self.bot.process_new_guest_message([make_message('продолжи', 42, 'private', guest_query_id='second', reply_to_message=previous.json, **{'from': user(43)})])
        self.assert_last_prompt('schizo')
        previous = make_message('offline answer', 42, 'private', message_id=300000, guest_bot_caller_user=user(43), **{'from': user(999, True)})
        await self.bot.process_new_guest_message([make_message('еще', 43, 'private', guest_query_id='third', reply_to_message=previous.json)])
        self.assert_last_prompt('schizo')
        other = make_message('другой чат', 43, 'private', guest_query_id='third', reply_to_message=previous.json, **{'from': user(44)})
        self.assertEqual(get_message_style(other).id, 'default')
        regular = make_message('обычная личка', 43, 'private', reply_to_message=previous.json, **{'from': user(43)})
        self.assertEqual(get_message_style(regular).id, 'default')

    async def test_guest_unknown_identifier_can_still_inherit_sent_response(self):
        self.bot.answer_guest_query.side_effect = None
        self.bot.answer_guest_query.return_value = SimpleNamespace(inline_message_id='unknown-layout')
        await self.bot.process_new_guest_message([make_message('начало', -10, 'group', guest_query_id='first')])
        set_user_style(42, 'default')
        previous = make_message('offline answer', -10, 'group', message_id=200000, guest_bot_caller_user=user(42), **{'from': user(999, True)})
        await self.bot.process_new_guest_message([make_message('продолжи', -10, 'group', guest_query_id='second', reply_to_message=previous.json, **{'from': user(43)})])
        self.assert_last_prompt('schizo')

    async def test_guest_media_fallback_inherits_style_of_branch(self):
        await self.bot.process_new_guest_message([make_message('начало', -10, 'group', guest_query_id='first')])
        previous = make_message('offline answer', -10, 'group', message_id=100000, guest_bot_caller_user=user(42), **{'from': user(999, True)})
        photo = [{'file_id': 'photo', 'file_unique_id': 'unique', 'width': 10, 'height': 10}]
        reply = make_message(None, -10, 'group', photo=photo, guest_query_id='second', reply_to_message=previous.json, **{'from': user(43)})
        with patch.object(config, 'OPENROUTER_API_KEY', ''):
            await self.bot.process_new_guest_message([reply])
        self.assertEqual(self.bot.edit_message_text.call_args.kwargs['rich_message'].markdown, FALLBACKS['vision_not_configured'])


class GuestIdentifierTests(unittest.TestCase):
    def test_modern_legacy_and_boxed_identifiers(self):
        for boxed in (False, True):
            self.assertEqual(guest_reply_message_id(inline_id(123, boxed)), 123)
            legacy = struct.pack('<iqq', 2, (42 << 32) | 123, 456)
            if boxed:
                legacy = struct.pack('<I', 0x890C3D89) + legacy
            value = base64.urlsafe_b64encode(legacy).decode().rstrip('=')
            self.assertEqual(guest_reply_message_id(value), 123)
        for value in ('invalid', '', '%%%'):
            self.assertIsNone(guest_reply_message_id(value))
