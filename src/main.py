import asyncio
import logging

import aiohttp
from telebot.async_telebot import AsyncTeleBot

import config
from database import initialize_database
from handlers.commands import register_command_handlers
from handlers.groups import register_group_handlers
from handlers.messages import register_message_handlers


async def main():
    initialize_database(config.DATABASE_PATH)
    bot = AsyncTeleBot(config.BOT_TOKEN)

    timeout = aiohttp.ClientTimeout(total=60)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            register_command_handlers(bot)
            register_message_handlers(bot, session)
            register_group_handlers(bot, session)

            logging.info('Bot starting...')

            await bot.infinity_polling(allowed_updates=['message', 'guest_message', 'my_chat_member'])
    finally:
        await bot.close_session()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    asyncio.run(main())
