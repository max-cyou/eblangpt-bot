import asyncio

import aiohttp

from services.ai import request_answer
from services.history import get_chat_lock, get_history, save_exchange


def register_message_handlers(bot, session):
    async def message_handler(message, bot):
        async with get_chat_lock(message.chat.id):
            history = get_history(message.chat.id)
            try:
                answer = await request_answer(message.text, session, history)
            except asyncio.TimeoutError:
                await bot.reply_to(message, 'слыш😈 ты че там промямлил💪 не слышно тебя')
                return
            except aiohttp.ClientResponseError:
                await bot.reply_to(message, 'э😈 сервер отвалился💪 попробуй позже')
                return

            await bot.reply_to(message, answer)
            save_exchange(message.chat.id, message.text, answer)

    bot.register_message_handler(message_handler,
        content_types=['text'],
        pass_bot=True,
    )
