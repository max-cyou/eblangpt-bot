import random

import config
from database import get_group_ban, get_user_ban
from services.context import get_object_field


BAN_REPLIES = (
    'слыш😈 пошел нахуй вась💪',
    'вась👍 ты в бане✅ пошел нахуй😈',
    'э😈 тебе тут не рады💪 пошел нахуй вась',
    'пошел нахуй😈 разговор окончен вась👍',
)


def ban_reply():
    return random.choice(BAN_REPLIES)


def user_is_banned(user_id):
    return bool(user_id and get_user_ban(config.DATABASE_PATH, user_id))


def chat_is_banned(chat):
    return get_object_field(chat, 'type') in ('group', 'supergroup') and bool(
        get_group_ban(config.DATABASE_PATH, get_object_field(chat, 'id'))
    )


def message_group_is_banned(message):
    return chat_is_banned(get_object_field(message, 'chat'))


def message_is_banned(message):
    raw = get_object_field(message, 'json') or {}
    caller = get_object_field(message, 'guest_bot_caller_user') or raw.get('guest_bot_caller_user')
    return any(
        user_is_banned(get_object_field(user, 'id'))
        for user in (get_object_field(message, 'from_user'), caller)
        if user is not None
    )
