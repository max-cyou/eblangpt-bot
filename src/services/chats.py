import asyncio
import random
import re

import config
from database import consume_group_random_reply, remember_chat
from services.context import full_name


GROUP_TRIGGER_PATTERN = re.compile(r'^\s*(?:вась|уась|еблан|гпт|вася)', re.IGNORECASE)
bot_users = {}
bot_user_locks = {}


async def get_bot_user(bot):
    async with bot_user_locks.setdefault(bot, asyncio.Lock()):
        if bot not in bot_users:
            bot_users[bot] = await bot.get_me()
    return bot_users[bot]


def remember_message(message):
    sender = message.from_user
    remember_chat(
        config.DATABASE_PATH, message.chat.id, message.chat.type,
        username=sender.username if sender and message.chat.type == 'private' else message.chat.username,
        title=message.chat.title or (full_name(sender) if sender else None),
    )


async def group_is_triggered(bot, message, text=''):
    current = await get_bot_user(bot)
    reply = message.reply_to_message
    return bool(
        (reply and reply.from_user and reply.from_user.id == current.id)
        or (current.username and re.search(rf'^\s*@{re.escape(current.username)}\b', text, re.I))
        or GROUP_TRIGGER_PATTERN.search(text)
    )


async def strip_bot_mention(bot, text):
    current = await get_bot_user(bot)
    if current.username:
        text = re.sub(rf'@{re.escape(current.username)}\b', '', text, flags=re.I)
    return text.strip()


def random_reply_due(chat_id):
    return consume_group_random_reply(
        config.DATABASE_PATH, chat_id,
        random.randint(config.GROUP_RANDOM_REPLY_MIN, config.GROUP_RANDOM_REPLY_MAX),
    )
