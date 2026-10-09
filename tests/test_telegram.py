import unittest
from unittest.mock import AsyncMock

from services.telegram import edit_text, send_text, text_chunks
from tests.helpers import BotTestMixin, make_message
from tests.test_admin_guest import telegram_error


class TelegramTests(BotTestMixin, unittest.IsolatedAsyncioTestCase):
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
