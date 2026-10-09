import asyncio

import aiohttp
from telebot.async_telebot import AsyncTeleBot

import config
from database import initialize_database
from handlers.commands import register_command_handlers
from handlers.messages import register_message_handlers


async def main():
    initialize_database(config.DATABASE_PATH)
    bot = AsyncTeleBot(config.BOT_TOKEN)

    timeout = aiohttp.ClientTimeout(total=60)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        register_command_handlers(bot)
        register_message_handlers(bot, session)

        print("Bot starting...")

        await bot.infinity_polling()

if __name__ == '__main__':
    asyncio.run(main())
