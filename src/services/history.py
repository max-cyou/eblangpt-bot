import asyncio
from weakref import WeakValueDictionary

import config
from database import append_history, delete_history, read_history

chat_locks = WeakValueDictionary()


def get_chat_lock(chat_id, thread_id=None):
    return chat_locks.setdefault((chat_id, thread_id or 0), asyncio.Lock())


def get_history(chat_id, thread_id=None):
    return read_history(config.DATABASE_PATH, chat_id, thread_id or 0)


def save_exchange(chat_id, user_text, answer, thread_id=None):
    append_history(
        config.DATABASE_PATH, chat_id, thread_id or 0,
        [{'role': 'user', 'content': user_text},
         {'role': 'assistant', 'content': answer}],
        config.HISTORY_LIMIT, config.CONTEXT_CHAR_LIMIT,
    )


def save_message(chat_id, text, thread_id=None):
    append_history(
        config.DATABASE_PATH, chat_id, thread_id or 0,
        [{'role': 'user', 'content': text}],
        config.HISTORY_LIMIT, config.CONTEXT_CHAR_LIMIT,
    )


def clear_history(chat_id, thread_id=None):
    delete_history(config.DATABASE_PATH, chat_id, thread_id or 0)
