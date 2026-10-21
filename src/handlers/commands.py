import logging

from telebot import types
from telebot.asyncio_helper import ApiTelegramException

import config
from services.chats import get_bot_user, remember_message
from services.history import clear_history, get_chat_lock
from services.permissions import is_admin
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
    return await telegram_call(
        bot.send_message, chat_id=message.chat.id, text=caption,
        reply_markup=keyboard, message_thread_id=message.message_thread_id,
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
        'а так же мой сурс - https://github.com/max-cyou/eblangpt-bot\n\n/help — команды все', keyboard,
    )
    if message.chat.type == 'private' and is_admin(message):
        await register_admin_command_menu(bot, message.chat.id)


async def clear_handler(message, bot):
    remember_message(message)
    async with get_chat_lock(message.chat.id, message.message_thread_id):
        clear_history(message.chat.id, message.message_thread_id)
        await send_text(bot, message, 'контекст стер✅ стиль на месте вась')


async def help_handler(message, bot):
    remember_message(message)
    await send_text(
        bot, message,
        '**слыш😈 вот команды вась**\n\n'
        '/start — знакомимся👍 погнали\n'
        '/help — сюда гляди если забыл команды\n'
        '/style — выбирай как мне базарить💪\n'
        '/clear — стираем память диалога✅ начнем заново\n\n'
        'пиши текст кидай пикчи войсы или файлы😈 разберемся вась',
    )


def register_command_handlers(bot):
    bot.register_message_handler(start_handler, commands=['start'], pass_bot=True)
    bot.register_message_handler(clear_handler, commands=['clear'], pass_bot=True)
    bot.register_message_handler(help_handler, commands=['help'], pass_bot=True)


def public_commands():
    return [
        types.BotCommand('start', 'знакомимся👍 погнали вась'),
        types.BotCommand('help', 'команды тут😈 гляди вась'),
        types.BotCommand('clear', 'стираем память✅ начнем заново'),
        types.BotCommand('style', 'выбирай как мне базарить💪'),
    ]


async def register_admin_command_menu(bot, chat_id):
    commands = public_commands() + [
        types.BotCommand('stats', 'циферки бота😈 только для админа'),
        types.BotCommand('broadcast', 'рассылка💪 только для админа'),
        types.BotCommand('ban', 'бан😈 только для админа'),
        types.BotCommand('unban', 'разбан💪 только для админа'),
        types.BotCommand('banlist', 'список банов😈 только для админа'),
        types.BotCommand('bangroup', 'группу в чс😈 только для админа'),
        types.BotCommand('unbangroup', 'убрать группу из чс💪 только для админа'),
    ]
    try:
        await telegram_call(bot.set_my_commands, commands=commands, scope=types.BotCommandScopeChat(chat_id))
    except ApiTelegramException as error:
        if error.error_code != 400 or 'chat not found' not in error.description.casefold():
            raise
        # An administrator who has not opened the bot yet gets the menu on /start.
        logger.warning('Admin command menu unavailable: private chat not found')


async def register_command_menu(bot):
    await telegram_call(bot.set_my_commands, commands=public_commands())
    if config.ADMIN_USER_ID:
        await register_admin_command_menu(bot, config.ADMIN_USER_ID)
