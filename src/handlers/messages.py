import config
from database import increment_counter
from services.context import get_message_content_text
from services.replies import answer_message


def private_prompt(message):
    text = get_message_content_text(message)
    reference = get_message_content_text(message.reply_to_message)
    if reference:
        return f'сообщение на которое ответил пользователь:\n{reference}\n\nзапрос пользователя:\n{text}'
    return text


def register_message_handlers(bot, session):
    async def message_handler(message):
        text = private_prompt(message)
        if not text.strip():
            return
        increment_counter(config.DATABASE_PATH, 'private_text_messages')
        await answer_message(bot, session, message, text)

    bot.register_message_handler(
        message_handler, content_types=['text', 'rich_message'], chat_types=['private'],
    )
