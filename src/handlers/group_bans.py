import logging
import re

from telebot import types, util

import config
from database import ban_group, unban_group
from handlers.admin import is_admin_user
from services.chats import get_bot_user
from services.bans import message_group_is_banned
from services.context import get_message_content_text, get_object_field
from services.errors import REQUEST_ERRORS, failure_details
from services.telegram import reply_options, telegram_call


logger = logging.getLogger(__name__)
GUEST_GROUP_COMMAND = re.compile(r'^(?:@([A-Za-z0-9_]+)\s+)?/(bangroup|unbangroup)(?:@([A-Za-z0-9_]+))?(?=\s|$)', re.I)


def group_ban_text(message, actor, remove=False, has_args=False):
    if not is_admin_user(actor):
        return 'тебе нельзя😈 чс групп только для админа вась'
    if message.chat.type not in ('group', 'supergroup'):
        return 'э😈 эту команду пиши прямо в группе вась'
    if has_args:
        return 'пиши `/unbangroup` без аргументов вась😈' if remove else 'пиши `/bangroup` без аргументов вась😈'
    if remove:
        removed = unban_group(config.DATABASE_PATH, message.chat.id)
        return 'группа разбанена✅ снова базарим вась💪' if removed else 'эта группа и так без бана вась👍'
    ban_group(config.DATABASE_PATH, message.chat.id, get_object_field(actor, 'id'))
    return '⛔ группа в чс✅ здесь больше не отвечаю вась'


async def group_ban_command(message, bot, remove=False):
    command = (message.text or '').split()[0]
    if '@' in command:
        current = await get_bot_user(bot)
        if command.split('@', 1)[1].casefold() != (current.username or '').casefold():
            return
    text = group_ban_text(message, message.from_user, remove, len((message.text or '').split()) != 1)
    # Moderation commands must remain usable after the group is blocked.
    await telegram_call(bot.send_message, text=text, parse_mode=None, **reply_options(message))


async def handle_guest_group_ban(message, bot):
    text = get_message_content_text(message)
    command = GUEST_GROUP_COMMAND.match(text)
    if not command:
        return False
    current = await get_bot_user(bot)
    for mention in (command[1], command[3]):
        if mention and mention.casefold() != (current.username or '').casefold():
            return False
    raw = get_object_field(message, 'json') or {}
    actor = get_object_field(message, 'guest_bot_caller_user') or raw.get('guest_bot_caller_user') or message.from_user
    answer = group_ban_text(message, actor, command[2].casefold() == 'unbangroup', bool(text[command.end():].strip()))
    result = types.InlineQueryResultArticle(
        id='guest-group-moderation', title='eblangpt',
        input_message_content=types.InputRichMessageContent(types.InputRichMessage(markdown=answer)),
    )
    try:
        await telegram_call(bot.answer_guest_query, guest_query_id=message.guest_query_id, result=result)
    except REQUEST_ERRORS as error:
        logger.warning('Guest group moderation reply failed: %s', failure_details(error))
    return True


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
