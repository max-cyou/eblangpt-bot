import logging
from contextlib import nullcontext

import config
from database import increment_counter
from services.ai import request_answer
from services.chats import remember_message
from services.context import format_user_message
from services.errors import REQUEST_ERRORS, failure_details, fallback_text
from services.history import get_chat_lock, get_history, save_exchange
from services.styles import format_style_answer, get_message_style, style_status_text
from services.telegram import finish_status, show_status, update_status


logger = logging.getLogger(__name__)


async def answer_message(bot, session, message, text, status=None, lock_held=False, style=None):
    remember_message(message)
    if message.chat.type == 'private':
        text = format_user_message(message, text)
    thread = message.message_thread_id
    async with (nullcontext() if lock_held else get_chat_lock(message.chat.id, thread)):
        history = get_history(message.chat.id, thread)
        style = style or get_message_style(message)
        increment_counter(config.DATABASE_PATH, 'generations')
        if status is None:
            status = await show_status(bot, message, style_status_text(style))

        async def update(partial):
            await update_status(bot, message, status, partial)

        try:
            answer = await request_answer(text, session, history, update, system_prompt=style.system_prompt)
            answer = format_style_answer(answer, history, style)
        except REQUEST_ERRORS as error:
            logger.warning('AI request failed: %s', failure_details(error))
            increment_counter(config.DATABASE_PATH, 'ai_errors')
            await finish_status(bot, message, status, fallback_text(error, style=style))
            return
        await finish_status(bot, message, status, answer)
        save_exchange(message.chat.id, text, answer, thread)
