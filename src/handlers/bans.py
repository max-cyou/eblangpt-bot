import logging
import re

from telebot import types, util
from telebot.asyncio_handler_backends import ContinueHandling

import config
from database import ban_user, find_user_by_username, get_known_user, unban_user
from handlers.admin import is_admin
from services.bans import ban_reply, message_is_banned
from services.chats import get_bot_user, group_is_triggered
from services.context import get_message_content_text
from services.errors import REQUEST_ERRORS, failure_details
from services.telegram import send_text, telegram_call
from services.users import remember_message_users


logger = logging.getLogger(__name__)
BOT_COMMAND = re.compile(r'^/(start|help|style|clear|stats|broadcast|ban|unban)(?:@([A-Za-z0-9_]+))?(?:\s|$)', re.I)


def ban_target(message, command):
    args = re.sub(rf'^/{command}(?:@[A-Za-z0-9_]+)?(?=\s|$)', '', message.text or '', count=1, flags=re.I).strip()
    # Explicit numeric IDs take precedence over a replied-to message.
    parts = args.split(maxsplit=1)
    if parts and parts[0].isascii() and parts[0].isdigit():
        user_id = int(parts[0])
        reason = parts[1] if len(parts) > 1 else ''
    elif parts and parts[0].startswith('@'):
        if not re.fullmatch(r'@[A-Za-z0-9_]{1,32}', parts[0]):
            raise ValueError('invalid_username')
        user_id = find_user_by_username(config.DATABASE_PATH, parts[0])
        if user_id is None:
            raise ValueError('username_unknown')
        reason = parts[1] if len(parts) > 1 else ''
    elif message.reply_to_message and message.reply_to_message.from_user:
        user_id = message.reply_to_message.from_user.id
        reason = args
    else:
        raise ValueError('target_missing')
    if not 0 < user_id < 2 ** 53:
        raise ValueError('invalid_id')
    if command == 'ban' and (not reason or len(reason) > 1000):
        raise ValueError('invalid_reason')
    if command == 'unban' and reason:
        raise ValueError('unexpected_reason')
    return user_id, reason


async def blocked_message(message, bot):
    if message.chat.type != 'private':
        text = get_message_content_text(message)
        command = BOT_COMMAND.match(text)
        addressed_command = bool(command)
        if command and command[2]:
            current = await get_bot_user(bot)
            addressed_command = command[2].casefold() == (current.username or '').casefold()
        if not addressed_command and not await group_is_triggered(bot, message, text):
            return
    await send_text(bot, message, ban_reply())


async def ban_handler(message, bot):
    if not is_admin(message):
        await send_text(bot, message, 'тебе нельзя😈 банить может только админ вась')
        return
    try:
        user_id, reason = ban_target(message, 'ban')
    except ValueError as error:
        if str(error) == 'username_unknown':
            await send_text(bot, message, 'не нашел однозначный ID по этому юзу😈 дай ID или ответь командой на его сообщение вась')
            return
        await send_text(bot, message, 'пиши `/ban @username причина`, `/ban user_id причина` или ответь `/ban причина` на сообщение вась😈 причина — до 1000 символов')
        return
    reference = message.reply_to_message
    target = reference.from_user if reference and reference.from_user and reference.from_user.id == user_id else None
    current = await get_bot_user(bot)
    known = get_known_user(config.DATABASE_PATH, user_id)
    known_admin = known and not config.ADMIN_USER_ID and config.ADMIN_USERNAME and (known[0] or '').casefold() == config.ADMIN_USERNAME
    if user_id in (message.from_user.id, config.ADMIN_USER_ID, current.id) or (known and (known[1] or known_admin)) or (target and (target.is_bot or is_admin(reference))):
        await send_text(bot, message, 'вась😈 себя админа и ботов не баним')
        return
    ban_user(config.DATABASE_PATH, user_id, reason, message.from_user.id)
    notification = f'⛔ вы были заблокированы ✅\n\nпричина: {reason}'
    notified = False
    try:
        await telegram_call(bot.send_message, chat_id=user_id, text=notification, parse_mode=None)
        notified = True
    except REQUEST_ERRORS as error:
        logger.warning('Ban notification failed: %s', failure_details(error))
        if target and message.chat.type != 'private':
            try:
                await telegram_call(
                    bot.send_message, chat_id=message.chat.id, text=notification, parse_mode=None,
                    message_thread_id=message.message_thread_id,
                    reply_parameters=types.ReplyParameters(
                        message_id=reference.message_id, allow_sending_without_reply=True,
                    ),
                )
                notified = True
            except REQUEST_ERRORS as error:
                logger.warning('Group ban notification failed: %s', failure_details(error))
    text = f'забанил {user_id}✅'
    if not notified:
        text += '\nуведомление не доставлено😈 бан все равно действует'
    await send_text(bot, message, text)


async def unban_handler(message, bot):
    if not is_admin(message):
        await send_text(bot, message, 'тебе нельзя😈 разбан только для админа вась')
        return
    try:
        user_id, _ = ban_target(message, 'unban')
    except ValueError as error:
        if str(error) == 'username_unknown':
            await send_text(bot, message, 'не нашел однозначный ID по этому юзу😈 дай ID или ответь командой на его сообщение вась')
            return
        await send_text(bot, message, 'пиши `/unban @username`, `/unban user_id` или ответь `/unban` на сообщение вась😈')
        return
    removed = unban_user(config.DATABASE_PATH, user_id)
    text = f'разбанил {user_id}✅' if removed else f'{user_id} и так без бана вась👍'
    if removed:
        try:
            await telegram_call(bot.send_message, chat_id=user_id, text='✅ вы были разблокированы\n\nслыш😈 можешь снова базарить вась💪', parse_mode=None)
        except REQUEST_ERRORS as error:
            logger.warning('Unban notification failed: %s', failure_details(error))
            text += '\nуведомление не доставлено😈 разбан все равно действует'
    await send_text(bot, message, text)


def register_ban_handlers(bot):
    async def track_users(message):
        remember_message_users(message)
        return ContinueHandling()

    bot.register_message_handler(
        track_users, func=lambda message: True,
        content_types=list(dict.fromkeys(util.content_type_media + util.content_type_service + ['rich_message'])),
    )
    # Must precede commands, text and media so blocked messages never reach them.
    bot.register_message_handler(
        blocked_message, func=message_is_banned, pass_bot=True,
        content_types=['text', 'rich_message', 'photo', 'voice', 'audio', 'document', 'location',
                       'sticker', 'video', 'animation', 'video_note', 'contact', 'dice', 'poll', 'venue'],
    )
    bot.register_message_handler(ban_handler, commands=['ban'], pass_bot=True)
    bot.register_message_handler(unban_handler, commands=['unban'], pass_bot=True)
