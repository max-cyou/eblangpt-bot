import asyncio

import aiohttp

from services.ai import request_answer


def register_message_handlers(bot, session):
    async def message_handler(message, bot):
        try:
            answer = await request_answer(message.text, session)
        except asyncio.TimeoutError:
            await bot.reply_to(message, 'слыш😈 ты че там промямлил💪 не слышно тебя')
            return
        except aiohttp.ClientResponseError:
            await bot.reply_to(message, 'э😈 сервер отвалился💪 попробуй позже')
            return

        await bot.reply_to(message, answer)

    bot.register_message_handler(message_handler,
        content_types=['text'],
        pass_bot=True,
    )
