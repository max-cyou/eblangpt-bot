import logging

import config
from database import increment_counter
from services.chats import group_is_triggered, random_reply_due, remember_message, strip_bot_mention
from services.context import format_group_message, get_message_content_text
from services.errors import REQUEST_ERRORS, failure_details, fallback_text
from services.history import get_chat_lock, save_message
from services.media import attachment_kind, prepare_media_prompt
from services.replies import answer_message
from services.telegram import AUDIO_STATUS_TEXT, IMAGE_STATUS_TEXT, finish_status, show_status


logger = logging.getLogger(__name__)


async def answer_media(bot, session, message, question='', source=None):
    source = source or message
    kind = attachment_kind(source)
    remember_message(message)
    status_text = {'audio': AUDIO_STATUS_TEXT, 'image': IMAGE_STATUS_TEXT}.get(kind)
    status = await show_status(bot, message, status_text) if status_text else None
    try:
        text, _ = await prepare_media_prompt(bot, session, message, question, source)
    except REQUEST_ERRORS as error:
        logger.warning('Attachment failed: %s', failure_details(error))
        await finish_status(bot, message, status, fallback_text(error, kind))
        return
    if source is not message:
        reference_text = get_message_content_text(source)
        if reference_text:
            text += f'\nтекст связанного сообщения:\n{reference_text}'
    if message.chat.type != 'private':
        text = format_group_message(message, text)
    await answer_message(bot, session, message, text, status)


def register_media_handlers(bot, session):
    async def private_media(message):
        await answer_media(bot, session, message, get_message_content_text(message))

    async def group_media(message):
        remember_message(message)
        if not message.from_user or message.from_user.is_bot:
            return
        caption = get_message_content_text(message)
        triggered = await group_is_triggered(bot, message, caption)
        random_due = random_reply_due(message.chat.id)
        if triggered or random_due:
            if random_due and not triggered:
                increment_counter(config.DATABASE_PATH, 'group_random_replies')
            await answer_media(bot, session, message, await strip_bot_mention(bot, caption))
            return
        kind = attachment_kind(message)
        if kind == 'image':
            text = f'отправил изображение с подписью: {caption}' if caption else 'отправил изображение'
        else:
            try:
                text, transcript = await prepare_media_prompt(bot, session, message, caption)
            except REQUEST_ERRORS as error:
                logger.warning('Passive attachment failed: %s', failure_details(error))
                return
            if kind == 'audio' and await group_is_triggered(bot, message, transcript):
                await answer_message(bot, session, message, format_group_message(message, text))
                return
        async with get_chat_lock(message.chat.id, message.message_thread_id):
            save_message(message.chat.id, format_group_message(message, text), message.message_thread_id)

    kinds = ['photo', 'voice', 'audio', 'document', 'location']
    bot.register_message_handler(private_media, content_types=kinds, chat_types=['private'])
    bot.register_message_handler(group_media, content_types=kinds, chat_types=['group', 'supergroup'])
