import logging

from telebot import types

import config
from database import increment_counter
from services.ai import request_answer
from services.chats import strip_bot_mention
from services.context import get_audio_attachment, get_image_attachment, get_message_content_text, get_object_field
from services.emojis import add_emojis_to_casual_answer
from services.errors import REQUEST_ERRORS, failure_details, fallback_text
from services.media import attachment_kind, prepare_media_prompt
from services.telegram import AUDIO_STATUS_TEXT, IMAGE_STATUS_TEXT, STREAM_STATUS_TEXT, edit_text, telegram_call, text_chunks


logger = logging.getLogger(__name__)


def guest_references(message):
    references = []
    for reference in (message.reply_to_message, message.external_reply):
        if reference:
            references.append(reference)
    raw = get_object_field(message, 'json') or {}
    for source in (message, raw):
        for reference in get_object_field(source, 'reference_messages', ()) or ():
            if isinstance(reference, dict) and 'message_id' in reference and 'chat' in reference:
                reference = types.Message.de_json(reference)
            if reference not in references:
                references.append(reference)
    return references


def guest_context(message, references):
    texts = []
    for reference in references:
        text = get_message_content_text(reference)
        if text and text not in texts:
            texts.append(text)
    quote = get_object_field(message.quote, 'text', '')
    if quote and quote not in texts:
        texts.append(quote)
    return '\n\n'.join(texts)


def guest_media_source(message, references):
    sources = [message, *references]
    for getter in (get_audio_attachment, get_image_attachment):
        for source in sources:
            if getter(source):
                return source
    for source in sources:
        if attachment_kind(source):
            return source
    return None


def register_guest_handlers(bot, session):
    async def guest_handler(message):
        increment_counter(config.DATABASE_PATH, 'guest_requests')
        user_text = await strip_bot_mention(bot, get_message_content_text(message)) or 'эй'
        references = guest_references(message)
        context = guest_context(message, references)
        source = guest_media_source(message, references)
        kind = attachment_kind(source) if source else 'ai'
        status_text = {'image': IMAGE_STATUS_TEXT, 'audio': AUDIO_STATUS_TEXT}.get(kind, STREAM_STATUS_TEXT)
        placeholder = types.InlineQueryResultArticle(
            id='guest-answer', title='eblangpt',
            input_message_content=types.InputRichMessageContent(types.InputRichMessage(markdown=status_text)),
        )
        try:
            sent = await telegram_call(bot.answer_guest_query, guest_query_id=message.guest_query_id, result=placeholder)
        except REQUEST_ERRORS as error:
            logger.warning('Guest placeholder failed: %s', failure_details(error))
            return

        async def update(text):
            try:
                await edit_text(bot, text[:2000], inline_message_id=sent.inline_message_id)
            except REQUEST_ERRORS as error:
                logger.debug('Guest stream update failed: %s', failure_details(error))

        try:
            ai_text = user_text
            if source:
                ai_text, _ = await prepare_media_prompt(bot, session, message, user_text, source)
            if context:
                ai_text = f'контекст связанных сообщений:\n{context}\n\nзапрос пользователя:\n{ai_text}'
        except REQUEST_ERRORS as error:
            logger.warning('Guest attachment failed: %s', failure_details(error))
            await update(fallback_text(error, kind))
            return
        increment_counter(config.DATABASE_PATH, 'generations')
        try:
            answer = await request_answer(ai_text, session, [], update)
            answer = add_emojis_to_casual_answer(answer, [])
        except REQUEST_ERRORS as error:
            logger.warning('Guest AI failed: %s', failure_details(error))
            increment_counter(config.DATABASE_PATH, 'ai_errors')
            answer = fallback_text(error)
        chunks = text_chunks(answer)
        if len(chunks) > 1:
            answer = chunks[0] + '\n\nответ обрезан по лимиту Telegram'
        try:
            await edit_text(bot, answer, inline_message_id=sent.inline_message_id)
        except REQUEST_ERRORS as error:
            logger.warning('Guest final reply failed: %s', failure_details(error))

    bot.register_guest_message_handler(guest_handler, func=lambda message: bool(message.guest_query_id))
