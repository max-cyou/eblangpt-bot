import asyncio
import logging

import aiohttp
from telebot import types
from telebot.asyncio_helper import ApiException, ApiTelegramException

from services.errors import failure_details
from services.branches import remember_reply_style


logger = logging.getLogger(__name__)
TELEGRAM_ERRORS = (ApiException, aiohttp.ClientError, TimeoutError)
STREAM_STATUS_TEXT = '😈 бжжж ответ calculating💪'
IMAGE_STATUS_TEXT = 'смотрю пикчу😈 погоди вась'
AUDIO_STATUS_TEXT = 'слушаю войс😈 погоди вась'


async def telegram_call(function, **kwargs):
    try:
        return await function(**kwargs)
    except ApiTelegramException as error:
        retry = (error.result_json.get('parameters') or {}).get('retry_after')
        if error.error_code != 429 or retry is None:
            raise
        await asyncio.sleep(retry)
        return await function(**kwargs)


def reply_options(message):
    return {
        'chat_id': message.chat.id,
        'message_thread_id': message.message_thread_id,
        'reply_parameters': types.ReplyParameters(
            message_id=message.message_id, allow_sending_without_reply=True,
        ),
    }


def text_chunks(text, limit=2000):
    # 2000 codepoints fit Telegram's 4096 UTF-16-unit text limit even with emoji.
    if len(text.encode('utf-16-le')) // 2 <= 4000:
        return [text]
    return [text[offset:offset + limit] for offset in range(0, len(text), limit)]


async def send_text(bot, message, text):
    sent = None
    for chunk in text_chunks(text):
        try:
            sent = await telegram_call(
                bot.send_rich_message,
                rich_message=types.InputRichMessage(markdown=chunk),
                **reply_options(message),
            )
        except ApiTelegramException as error:
            if error.error_code != 400:
                raise
            sent = await telegram_call(bot.send_message, text=chunk, parse_mode=None, **reply_options(message))
        remember_reply_style(message, sent)
    return sent


async def edit_text(bot, text, **target):
    try:
        return await telegram_call(
            bot.edit_message_text, rich_message=types.InputRichMessage(markdown=text), **target,
        )
    except ApiTelegramException as error:
        if error.error_code != 400:
            raise
        if 'message is not modified' in error.description.casefold():
            return None
        return await telegram_call(bot.edit_message_text, text=text, parse_mode=None, **target)


async def show_status(bot, message, text=STREAM_STATUS_TEXT):
    if message.chat.type == 'private':
        try:
            await bot.send_rich_message_draft(
                chat_id=message.chat.id, draft_id=message.message_id,
                message_thread_id=message.message_thread_id,
                rich_message=types.InputRichMessage(
                    blocks=[types.InputRichBlockThinking(text=text)],
                ),
            )
        except TELEGRAM_ERRORS:
            try:
                await bot.send_chat_action(message.chat.id, 'typing', message_thread_id=message.message_thread_id)
            except TELEGRAM_ERRORS:
                pass
        return None
    return await send_text(bot, message, text)


async def update_status(bot, message, status, text):
    try:
        if message.chat.type == 'private':
            await bot.send_rich_message_draft(
                chat_id=message.chat.id, draft_id=message.message_id,
                message_thread_id=message.message_thread_id,
                rich_message=types.InputRichMessage(markdown=text[:2000]),
            )
        elif status:
            await edit_text(bot, text[:2000], chat_id=message.chat.id, message_id=status.message_id)
    except TELEGRAM_ERRORS as error:
        logger.debug('Stream update failed: %s', failure_details(error))


async def finish_status(bot, message, status, text):
    if status is None:
        return await send_text(bot, message, text)
    chunks = text_chunks(text)
    await edit_text(bot, chunks[0], chat_id=message.chat.id, message_id=status.message_id)
    for chunk in chunks[1:]:
        await send_text(bot, message, chunk)
