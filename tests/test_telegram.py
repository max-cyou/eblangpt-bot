import unittest
from unittest.mock import AsyncMock

from services.telegram import (
    AUDIO_STATUS_TEXT, IMAGE_STATUS_TEXT, STREAM_STATUS_TEXT,
    edit_text, send_text, show_status, text_chunks, update_status,
)
from tests.helpers import BotTestMixin, make_message
from tests.test_admin_guest import telegram_error


class TelegramTests(BotTestMixin, unittest.IsolatedAsyncioTestCase):
    async def test_private_status_uses_native_thinking_block(self):
        message = make_message('test')
        for text in (STREAM_STATUS_TEXT, IMAGE_STATUS_TEXT, AUDIO_STATUS_TEXT):
            self.bot.send_rich_message_draft.reset_mock()
            await show_status(self.bot, message, text)
            payload = self.bot.send_rich_message_draft.call_args.kwargs['rich_message'].to_dict()
            self.assertEqual(payload, {'blocks': [{'type': 'thinking', 'text': text}]})
            self.bot.send_rich_message.assert_not_awaited()

    async def test_streamed_answer_replaces_thinking_with_markdown(self):
        message = make_message('test')
        await show_status(self.bot, message)
        await update_status(self.bot, message, None, 'готовый ответ')
        payload = self.bot.send_rich_message_draft.call_args.kwargs['rich_message'].to_dict()
        self.assertEqual(payload, {'markdown': 'готовый ответ'})

    async def test_group_status_does_not_use_draft_only_thinking_block(self):
        await show_status(self.bot, make_message('test', -10, 'group'))
        self.bot.send_rich_message_draft.assert_not_awaited()
        payload = self.bot.send_rich_message.call_args.kwargs['rich_message'].to_dict()
        self.assertEqual(payload, {'markdown': STREAM_STATUS_TEXT})

    async def test_rich_falls_back_to_plain_and_preserves_topic(self):
        self.bot.send_rich_message.side_effect = telegram_error(400)
        message = make_message('test', -10, 'supergroup', message_thread_id=17, is_topic_message=True)
        await send_text(self.bot, message, '**text**')
        self.assertEqual(self.bot.send_message.call_args.kwargs['text'], '**text**')
        self.assertEqual(self.bot.send_message.call_args.kwargs['message_thread_id'], 17)

    async def test_not_modified_edit_is_success(self):
        self.bot.edit_message_text.side_effect = telegram_error(400, 'Bad Request: message is not modified')
        await edit_text(self.bot, 'same', inline_message_id='guest')
        self.bot.edit_message_text.assert_awaited_once()

    def test_long_unicode_replies_fit_telegram_limit(self):
        text = '😈' * 5000
        chunks = text_chunks(text)
        self.assertEqual(''.join(chunks), text)
        self.assertTrue(all(len(chunk.encode('utf-16-le')) // 2 <= 4096 for chunk in chunks))
