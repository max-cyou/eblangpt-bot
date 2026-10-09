import logging

import config
from database import increment_counter
from services.ai import request_answer
from services.chats import remember_message
from services.emojis import add_emojis_to_casual_answer
from services.errors import REQUEST_ERRORS, failure_details, fallback_text
from services.history import get_chat_lock, get_history, save_exchange
from services.telegram import finish_status, show_status, update_status


logger = logging.getLogger(__name__)


async def answer_message(bot, session, message, text, status=None):
    remember_message(message)
    thread = message.message_thread_id
    async with get_chat_lock(message.chat.id, thread):
        history = get_history(message.chat.id, thread)
        increment_counter(config.DATABASE_PATH, 'generations')
        if status is None:
            status = await show_status(bot, message)

        async def update(partial):
            await update_status(bot, message, status, partial)

        try:
            answer = await request_answer(text, session, history, update)
            answer = add_emojis_to_casual_answer(answer, history)
        except REQUEST_ERRORS as error:
            logger.warning('AI request failed: %s', failure_details(error))
            increment_counter(config.DATABASE_PATH, 'ai_errors')
            await finish_status(bot, message, status, fallback_text(error))
            return
        await finish_status(bot, message, status, answer)
        save_exchange(message.chat.id, text, answer, thread)
