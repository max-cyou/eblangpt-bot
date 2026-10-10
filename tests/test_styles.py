import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiohttp

import config
from prompts import default as prompt
from database import initialize_database, set_user_style_id
from services.history import get_history, save_exchange
from services.styles import get_user_style, set_user_style
from fallbacks.common import FALLBACKS as COMMON_FALLBACKS
from fallbacks.schizo import FALLBACKS as SCHIZO_FALLBACKS
from styles import Style, get_style
from services.errors import fallback_text, failure_details
from services.styles import format_style_answer
from handlers.styles import register_style_handlers
from handlers.commands import register_command_handlers
from handlers.messages import register_message_handlers
from handlers.media import register_media_handlers
from handlers.guest import register_guest_handlers
from tests.helpers import BotTestMixin, Response, make_message


class StyleSettingsTests(BotTestMixin, unittest.TestCase):
    def test_default_and_removed_styles(self):
        self.assertEqual(get_user_style(42).system_prompt, prompt.SYSTEM_PROMPT)
        set_user_style_id(config.DATABASE_PATH, 42, 'removed-style')
        self.assertEqual(get_user_style(42).id, 'default')
        with self.assertRaises(ValueError):
            set_user_style(42, 'unknown')

    def test_choice_persists_and_does_not_clear_history(self):
        save_exchange(1, 'question', 'answer')
        set_user_style(42, 'schizo')
        initialize_database(config.DATABASE_PATH)
        self.assertEqual(get_user_style(42), get_style('schizo'))
        self.assertEqual(get_user_style(43).id, 'default')
        self.assertEqual(len(get_history(1)), 2)


class StyleHandlerTests(BotTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        register_command_handlers(self.bot)
        register_style_handlers(self.bot)
        register_message_handlers(self.bot, self.session)
        register_media_handlers(self.bot, self.session)
        register_guest_handlers(self.bot, self.session)
        self.bot.answer_callback_query = AsyncMock()
        self.bot.answer_guest_query = AsyncMock(return_value=SimpleNamespace(inline_message_id='inline'))

    async def test_menu_selection_and_group_ownership(self):
        await self.bot.process_new_messages([make_message('/style', -10, 'group')])
        menu = self.bot.send_message.call_args.kwargs['reply_markup']
        self.assertEqual(menu.keyboard[1][0].callback_data, 'style:42:schizo')
        select = self.bot.callback_query_handlers[0]['function']
        call = SimpleNamespace(id='query', data='style:42:schizo', from_user=SimpleNamespace(id=43), message=make_message('/style', -10, 'group'))
        await select(call)
        self.assertEqual(get_user_style(42).id, 'default')
        self.bot.answer_callback_query.assert_awaited_with(callback_query_id='query', text='вась😈 это чужое меню💪 свое открывай через /style', show_alert=True)
        call.from_user.id = 42
        await select(call)
        self.assertEqual(get_user_style(42).id, 'schizo')
        self.assertEqual(self.bot.edit_message_text.call_args.kwargs['reply_markup'].keyboard[1][0].text, f'✅ {get_style("schizo").name}')

    async def test_removed_and_malformed_buttons_do_not_change_choice(self):
        select = self.bot.callback_query_handlers[0]['function']
        for data in ('style:42:removed', 'style:bad:schizo', 'style:42:schizo:extra'):
            await select(SimpleNamespace(id='query', data=data, from_user=SimpleNamespace(id=42), message=None))
        self.assertEqual(get_user_style(42).id, 'default')
        self.bot.edit_message_text.assert_not_awaited()

    async def test_clear_keeps_selected_style(self):
        set_user_style(42, 'schizo')
        save_exchange(1, 'question', 'answer')
        await self.bot.process_new_messages([make_message('/clear')])
        self.assertEqual(get_history(1), [])
        self.assertEqual(get_user_style(42).id, 'schizo')

    async def test_text_media_and_guest_use_authors_prompt(self):
        set_user_style(42, 'schizo')
        await self.bot.process_new_messages([make_message('hello')])
        await self.bot.process_new_messages([make_message(None, location={'latitude': 55.7, 'longitude': 37.6})])
        await self.bot.process_new_guest_message([make_message('hello', guest_query_id='guest')])
        self.assertEqual(len(self.session.calls), 3)
        for _, arguments in self.session.calls:
            self.assertEqual(arguments['json']['messages'][0]['content'], get_style('schizo').system_prompt)
        self.assertEqual(self.bot.send_rich_message.call_args.kwargs['rich_message'].markdown, 'offline answer')
        self.assertEqual(self.bot.edit_message_text.call_args.kwargs['rich_message'].markdown, 'offline answer')

    async def test_selected_style_fallbacks_for_ai_media_and_guest(self):
        set_user_style(42, 'schizo')
        self.session.responses = [Response(status=503)]
        await self.bot.process_new_messages([make_message('fail')])
        self.assertEqual(self.bot.send_rich_message.call_args.kwargs['rich_message'].markdown, SCHIZO_FALLBACKS['server'])
        await self.bot.process_new_guest_message([make_message('fail', guest_query_id='guest')])
        self.assertEqual(self.bot.edit_message_text.call_args.kwargs['rich_message'].markdown, SCHIZO_FALLBACKS['server'])
        photo = [{'file_id': 'photo', 'file_unique_id': 'unique', 'width': 10, 'height': 10}]
        with patch.object(config, 'OPENROUTER_API_KEY', ''):
            await self.bot.process_new_messages([make_message(None, photo=photo)])
            self.assertEqual(self.bot.send_rich_message.call_args.kwargs['rich_message'].markdown, SCHIZO_FALLBACKS['vision_not_configured'])
            await self.bot.process_new_guest_message([make_message(None, photo=photo, guest_query_id='guest')])
            self.assertEqual(self.bot.edit_message_text.call_args.kwargs['rich_message'].markdown, SCHIZO_FALLBACKS['vision_not_configured'])

    async def test_group_style_belongs_to_request_author(self):
        from handlers.groups import register_group_handlers
        register_group_handlers(self.bot, self.session)
        set_user_style(42, 'schizo')
        await self.bot.process_new_messages([make_message('вась hello', -10, 'group')])
        self.assertEqual(self.session.calls[-1][1]['json']['messages'][0]['content'], get_style('schizo').system_prompt)
        other = make_message('вась hello', -10, 'group')
        other.from_user.id = 43
        await self.bot.process_new_messages([other])
        self.assertEqual(self.session.calls[-1][1]['json']['messages'][0]['content'], prompt.SYSTEM_PROMPT)


class StyleFormattingTests(unittest.TestCase):
    def test_failure_reason_does_not_expose_external_details(self):
        self.assertIn('reason=empty_answer', failure_details(ValueError('Provider returned an empty answer')))
        self.assertEqual(failure_details(ValueError('private URL or payload')), 'ValueError, status=None')

    def test_custom_fallbacks_and_neutral_defaults(self):
        custom = Style('custom', 'Custom', 'Description', 'Prompt', fallbacks={'timeout': 'custom timeout'})
        self.assertEqual(fallback_text(TimeoutError(), style=custom), 'custom timeout')
        self.assertEqual(fallback_text(ValueError(), 'image', custom), COMMON_FALLBACKS['image'])
        self.assertEqual(fallback_text(aiohttp.ClientResponseError(None, (), status=429), style=custom), COMMON_FALLBACKS['rate_limit'])

    def test_style_without_auto_emojis_does_not_modify_answer(self):
        self.assertEqual(format_style_answer('ordinary answer', [], get_style('schizo')), 'ordinary answer')
        self.assertEqual(fallback_text(TimeoutError()), 'слыш😈 модель задумалась💪 попробуй чуть позже')
