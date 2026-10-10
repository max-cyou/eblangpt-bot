import asyncio
import base64
import os

import aiohttp

import config
from database import increment_counter
from services.ai import request_slots, response_text
from services.errors import REQUEST_ERRORS
from services.retry import retry_once
from services.context import (
    format_audio_prompt, format_document_prompt, format_location,
    get_audio_attachment, get_audio_format, get_image_attachment,
    get_message_content_text,
)


TEXT_FILE_EXTENSIONS = {
    '.c', '.cfg', '.conf', '.cpp', '.cs', '.css', '.csv', '.go', '.h', '.hpp',
    '.html', '.ini', '.java', '.js', '.json', '.jsx', '.kt', '.log', '.lua',
    '.md', '.php', '.ps1', '.py', '.rb', '.rs', '.sh', '.sql', '.swift', '.tex',
    '.toml', '.ts', '.tsx', '.txt', '.xml', '.yaml', '.yml',
}
IMAGE_RECOGNITION_TIMEOUT = 10


def attachment_kind(message):
    if get_audio_attachment(message):
        return 'audio'
    if get_image_attachment(message):
        return 'image'
    if getattr(message, 'document', None):
        return 'document'
    if getattr(message, 'location', None):
        return 'location'
    return None


async def download_attachment(bot, attachment, limit, kind):
    if getattr(attachment, 'file_size', 0) and attachment.file_size > limit:
        raise ValueError(f'{kind}_too_large')
    file = await bot.get_file(attachment.file_id)
    if file.file_size and file.file_size > limit:
        raise ValueError(f'{kind}_too_large')
    raw = await bot.download_file(file.file_path)
    if len(raw) > limit:
        raise ValueError(f'{kind}_too_large')
    return raw


async def recognize_image(bot, session, photo, question=''):
    async with asyncio.timeout(IMAGE_RECOGNITION_TIMEOUT):
        return await _recognize_image(bot, session, photo, question)


async def _recognize_image(bot, session, photo, question):
    if not config.OPENROUTER_API_KEY:
        raise RuntimeError('vision_not_configured')
    raw = await download_attachment(bot, photo, config.IMAGE_MAX_BYTES, 'image')
    mime = getattr(photo, 'mime_type', None) or 'image/jpeg'
    if not mime.startswith('image/'):
        mime = 'image/jpeg'
    data = base64.b64encode(raw).decode('ascii')
    payload = {
        'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': (
                'Подробно и объективно опиши изображение. Перепиши различимый текст. '
                f'Укажи факты для ответа на вопрос: {question or "что изображено"}'
            )},
            {'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{data}'}},
        ]}],
        'max_tokens': 700, 'temperature': 0.2,
        'reasoning': {'effort': 'none', 'exclude': True},
    }
    headers = {
        'Authorization': f'Bearer {config.OPENROUTER_API_KEY}',
        'HTTP-Referer': 'https://t.me/', 'X-Title': 'EblanGPT',
    }
    models = dict.fromkeys(model for model in (
        config.OPENROUTER_VISION_MODEL, *config.OPENROUTER_VISION_FALLBACK_MODELS,
    ) if model)
    if not models:
        raise RuntimeError('No vision models configured')
    async def request_description():
        async with request_slots:
            async with session.post(config.OPENROUTER_CHAT_URL, json=dict(payload), headers=headers) as response:
                response.raise_for_status()
                result = await response.json()
        # Some vision providers return content as a list of text blocks.
        try:
            content = result['choices'][0]['message']['content']
            if isinstance(content, list):
                result['choices'][0]['message']['content'] = '\n'.join(
                    item.get('text', '') for item in content if isinstance(item, dict) and item.get('type') == 'text'
                )
        except (KeyError, IndexError, TypeError) as error:
            raise ValueError('Invalid vision response') from error
        description = response_text(result).strip()
        if len(description) < 20:
            raise ValueError('Vision description is empty')
        return description

    while True:
        for model in models:
            payload['model'] = model
            try:
                return await retry_once(request_description)
            except (aiohttp.ClientError, TimeoutError, ValueError):
                # The shared deadline also interrupts a stalled request.
                await asyncio.sleep(0)


async def transcribe_audio(bot, session, audio):
    if not config.GROQ_API_KEY:
        raise RuntimeError('audio_not_configured')
    raw = await download_attachment(bot, audio, config.AUDIO_MAX_BYTES, 'audio')
    audio_format = get_audio_format(audio)
    async def request_transcription():
        form = aiohttp.FormData()
        form.add_field('file', raw, filename=f'voice.{audio_format}',
                       content_type=getattr(audio, 'mime_type', None) or f'audio/{audio_format}')
        form.add_field('model', config.GROQ_TRANSCRIPT_MODEL)
        form.add_field('response_format', 'json')
        form.add_field('temperature', '0')
        async with request_slots:
            async with session.post(config.GROQ_TRANSCRIPT_URL, data=form,
                                    headers={'Authorization': f'Bearer {config.GROQ_API_KEY}'}) as response:
                response.raise_for_status()
                result = await response.json()
        text = result.get('text') if isinstance(result, dict) else None
        if not isinstance(text, str) or not text.strip() or text.strip().casefold() == '[речь не распознана]':
            raise ValueError('Empty audio transcription')
        return text.strip()

    return await retry_once(request_transcription)


def document_is_text(document):
    extension = os.path.splitext(document.file_name or '')[1].casefold()
    mime = (document.mime_type or '').casefold()
    return extension in TEXT_FILE_EXTENSIONS or mime.startswith('text/') or mime in {
        'application/json', 'application/xml', 'application/x-yaml',
    }


async def read_text_document(bot, document):
    if not document_is_text(document):
        raise ValueError('document_not_text')
    raw = await download_attachment(bot, document, config.TEXT_FILE_MAX_BYTES, 'document')
    text = None
    for encoding in ('utf-8-sig', 'utf-8', 'cp1251'):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError('Unknown document encoding')
    if len(text) > config.TEXT_FILE_MAX_CHARS:
        return text[:config.TEXT_FILE_MAX_CHARS] + '\n[остаток файла обрезан по лимиту]'
    return text


async def prepare_media_prompt(bot, session, message, question='', source=None):
    source = source or message
    kind = attachment_kind(source)
    try:
        if kind == 'audio':
            transcript = await transcribe_audio(bot, session, get_audio_attachment(source))
            increment_counter(config.DATABASE_PATH, 'audio_transcriptions')
            return format_audio_prompt(transcript, question), transcript
        if kind == 'image':
            description = await recognize_image(bot, session, get_image_attachment(source), question)
            increment_counter(config.DATABASE_PATH, 'images_recognized')
            return (
                'пользователь отправил изображение\n'
                f'<описание_изображения>{description}</описание_изображения>\n'
                f'вопрос пользователя: {question or "что здесь изображено"}', ''
            )
        if kind == 'document':
            content = await read_text_document(bot, source.document)
            increment_counter(config.DATABASE_PATH, 'text_files')
            text = format_document_prompt(source, content)
            if question and question != (source.caption or '').strip():
                text += f'\nвопрос пользователя: {question}'
            return text, ''
        if kind == 'location':
            increment_counter(config.DATABASE_PATH, 'locations')
            return format_location(source), ''
    except REQUEST_ERRORS:
        if kind in ('audio', 'image'):
            increment_counter(config.DATABASE_PATH, f'{kind}_errors')
        raise
    return question or get_message_content_text(source) or 'эй', ''
