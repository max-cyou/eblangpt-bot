from telebot import util

import config
from database import ban_group, unban_group
from handlers.admin import is_admin
from services.chats import get_bot_user
from services.bans import message_group_is_banned
from services.telegram import reply_options, telegram_call


async def group_ban_command(message, bot, remove=False):
    command = (message.text or '').split()[0]
    if '@' in command:
        current = await get_bot_user(bot)
        if command.split('@', 1)[1].casefold() != (current.username or '').casefold():
            return
    if not is_admin(message):
        text = 'тебе нельзя😈 чс групп только для админа вась'
    elif message.chat.type not in ('group', 'supergroup'):
        text = 'э😈 эту команду пиши прямо в группе где я участник вась'
    elif len((message.text or '').split()) != 1:
        text = 'пиши `/unbangroup` без аргументов вась😈' if remove else 'пиши `/bangroup` без аргументов вась😈'
    elif remove:
        removed = unban_group(config.DATABASE_PATH, message.chat.id)
        text = 'группа разбанена✅ снова базарим вась💪' if removed else 'эта группа и так без бана вась👍'
    else:
        ban_group(config.DATABASE_PATH, message.chat.id, message.from_user.id)
        text = '⛔ группа в чс✅ здесь больше не отвечаю вась'
    # Moderation commands must remain usable after the group is blocked.
    await telegram_call(bot.send_message, text=text, parse_mode=None, **reply_options(message))


async def bangroup_handler(message, bot):
    await group_ban_command(message, bot)


async def unbangroup_handler(message, bot):
    await group_ban_command(message, bot, remove=True)


def register_group_ban_handlers(bot):
    bot.register_message_handler(bangroup_handler, commands=['bangroup'], pass_bot=True)
    bot.register_message_handler(unbangroup_handler, commands=['unbangroup'], pass_bot=True)

    async def ignore_group(message):
        return

    bot.register_message_handler(
        ignore_group, func=message_group_is_banned,
        content_types=list(dict.fromkeys(util.content_type_media + util.content_type_service + ['rich_message'])),
    )
