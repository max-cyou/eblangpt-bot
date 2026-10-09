import asyncio

from telebot.async_telebot import AsyncTeleBot

import config
from handlers.commands import register_command_handlers
from handlers.messages import register_message_handlers


async def main():
    bot = AsyncTeleBot(config.BOT_TOKEN)

    register_command_handlers(bot)
    register_message_handlers(bot)
    print("Bot starting...")

    await bot.infinity_polling()

if __name__ == '__main__':
    asyncio.run(main())
