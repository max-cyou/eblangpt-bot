import config
from database import increment_counter
from services.chats import group_is_triggered, random_reply_due, remember_message, strip_bot_mention
from services.context import format_group_message, get_message_content_text
from services.history import get_chat_lock, save_message
from services.replies import answer_message
from handlers.media import answer_media
from services.media import attachment_kind
from services.styles import get_message_style


async def remember_group_text(message, text):
    async with get_chat_lock(message.chat.id, message.message_thread_id):
        save_message(message.chat.id, format_group_message(message, text), message.message_thread_id)


def register_group_handlers(bot, session):
    async def group_text(message):
        remember_message(message)
        text = get_message_content_text(message)
        if not text or not message.from_user:
            return
        increment_counter(config.DATABASE_PATH, 'group_text_messages')
        if message.from_user.is_bot:
            await remember_group_text(message, text)
            return
        get_message_style(message)
        triggered = await group_is_triggered(bot, message, text)
        random_due = random_reply_due(message.chat.id)
        if not triggered and not random_due:
            await remember_group_text(message, text)
            return
        if random_due and not triggered:
            increment_counter(config.DATABASE_PATH, 'group_random_replies')
        text = await strip_bot_mention(bot, text)
        reference = message.reply_to_message
        if reference and attachment_kind(reference):
            await answer_media(bot, session, message, text, reference)
            return
        await answer_message(bot, session, message, format_group_message(message, text or 'эй'))

    bot.register_message_handler(
        group_text, content_types=['text', 'rich_message'], chat_types=['group', 'supergroup'],
    )
