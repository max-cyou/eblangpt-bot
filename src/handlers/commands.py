import logging

from telebot import types
from telebot.asyncio_helper import ApiTelegramException

import config
from services.chats import get_bot_user, remember_message
from services.history import clear_history, get_chat_lock
from services.telegram import send_text, telegram_call


logger = logging.getLogger(__name__)


async def send_picture_or_text(bot, message, path, caption, keyboard=None):
    try:
        with path.open('rb') as image:
            return await telegram_call(
                bot.send_photo, chat_id=message.chat.id, photo=image, caption=caption,
                message_thread_id=message.message_thread_id, reply_markup=keyboard,
            )
    except OSError:
        logger.warning('Welcome image is unavailable')
    except ApiTelegramException as error:
        if error.error_code != 400:
            raise
    return await bot.send_message(
        message.chat.id, caption, reply_markup=keyboard, message_thread_id=message.message_thread_id,
    )


async def start_handler(message, bot):
    remember_message(message)
    current = await get_bot_user(bot)
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(types.InlineKeyboardButton('подписка💪', url='https://t.me/maxcyou'))
    if current.username:
        keyboard.row(types.InlineKeyboardButton('add в группу👍', url=f'https://t.me/{current.username}?startgroup=true'))
    await send_picture_or_text(
        bot, message, config.START_IMAGE_PATH,
        'вась👍 добавь меня в группу✅ или пиши тут\n\n'
        'я умею читать писать и отвечать в guest режиме\n'
        'читать сообщения в группах файлы и геолокацию\n'
        'смотреть пикчи и слушать голосовые\n\n'
        '/clear — очистить контекст\n\nа так же мой сурс - https://github.com/max-cyou/eblangpt-bot!', keyboard,
    )


async def clear_handler(message, bot):
    remember_message(message)
    async with get_chat_lock(message.chat.id, message.message_thread_id):
        clear_history(message.chat.id, message.message_thread_id)
        await send_text(bot, message, 'контекст очищен✅ вась')


def register_command_handlers(bot):
    bot.register_message_handler(start_handler, commands=['start'], pass_bot=True)
    bot.register_message_handler(clear_handler, commands=['clear'], pass_bot=True)


async def register_command_menu(bot):
    await bot.set_my_commands([
        types.BotCommand('start', 'запустить бота'),
        types.BotCommand('clear', 'очистить контекст диалога'),
        types.BotCommand('stats', 'статистика бота для админа'),
        types.BotCommand('broadcast', 'рассылка для админа'),
    ])
