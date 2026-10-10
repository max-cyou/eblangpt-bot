import asyncio
import logging

import aiohttp
from telebot.async_telebot import AsyncTeleBot

import config
from database import initialize_database
from handlers.commands import register_command_handlers, register_command_menu
from handlers.admin import register_admin_handlers
from handlers.events import register_event_handlers
from handlers.guest import register_guest_handlers
from handlers.groups import register_group_handlers
from handlers.messages import register_message_handlers
from handlers.media import register_media_handlers
from handlers.styles import register_style_handlers
from services.health import notify_ready


async def main():
    initialize_database(config.DATABASE_PATH)
    bot = AsyncTeleBot(config.BOT_TOKEN)

    timeout = aiohttp.ClientTimeout(total=60)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            register_command_handlers(bot)
            register_style_handlers(bot)
            register_admin_handlers(bot)
            register_event_handlers(bot)
            register_message_handlers(bot, session)
            register_group_handlers(bot, session)
            register_media_handlers(bot, session)
            register_guest_handlers(bot, session)
            await register_command_menu(bot)

            logging.info('Bot starting...')
            notify_ready()

            await bot.infinity_polling(allowed_updates=['message', 'guest_message', 'my_chat_member', 'callback_query'])
    finally:
        await bot.close_session()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    asyncio.run(main())
