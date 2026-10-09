import asyncio
import os

from dotenv import load_dotenv
from telebot.async_telebot import AsyncTeleBot

from handlers.commands import register_command_handlers
from handlers.messages import register_message_handlers

load_dotenv()

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

async def main():
    bot = AsyncTeleBot(BOT_TOKEN)

    register_command_handlers(bot)
    register_message_handlers(bot)
    print("Bot starting...")

    await bot.infinity_polling()

if __name__ == '__main__':
    if BOT_TOKEN.strip():
        asyncio.run(main())
    else:
        raise ValueError("Error: Bot token not found.")
