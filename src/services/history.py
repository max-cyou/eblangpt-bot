import asyncio


HISTORY_LIMIT = 30
chat_histories = {}
chat_locks = {}


def get_chat_lock(chat_id):
    return chat_locks.setdefault(chat_id, asyncio.Lock())


def get_history(chat_id):
    return [message.copy() for message in chat_histories.get(chat_id, [])]


def save_exchange(chat_id, user_text, answer):
    history = chat_histories.setdefault(chat_id, [])
    history.extend([
        {'role': 'user', 'content': user_text},
        {'role': 'assistant', 'content': answer},
    ])
    chat_histories[chat_id] = history[-HISTORY_LIMIT:]


def clear_history(chat_id):
    chat_histories.pop(chat_id, None)
