import os

def format_group_message(message, text):
    sender = message.from_user
    if sender is None:
        return text

    sender_name = full_name(sender) or 'без имени'
    sender_username = f'@{sender.username}' if sender.username else 'нет'
    sender_mention = (
        f'@{sender.username}'
        if sender.username
        else f'[{sender_name}](tg://user?id={sender.id})'
    )
    reply_context = ''
    reply = message.reply_to_message
    if reply is not None:
        reply_sender = reply.from_user
        reply_sender_name = (
            full_name(reply_sender)
            if reply_sender is not None
            else 'неизвестный отправитель'
        )
        reply_sender_username = (
            f'@{reply_sender.username}'
            if reply_sender is not None and reply_sender.username
            else 'нет'
        )
        reply_text = get_message_content_text(reply) or '[нет текста]'
        reply_context = (
            '<ответ_на_сообщение>\n'
            f'имя: {reply_sender_name}\n'
            f'username: {reply_sender_username}\n'
            f'текст: {reply_text}\n'
            '</ответ_на_сообщение>\n'
        )

    return (
        '<сообщение_из_группы>\n'
        f'имя: {sender_name}\n'
        f'username: {sender_username}\n'
        f'упоминание: {sender_mention}\n'
        f'telegram_id: {sender.id}\n'
        f'{reply_context}'
        f'текст: {text}\n'
        '</сообщение_из_группы>'
    )

def get_object_field(value, name, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)

def rich_content_to_text(value):
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return '\n'.join(
            part
            for item in value
            if (part := rich_content_to_text(item)).strip()
        )

    text = get_object_field(value, 'text')
    if text is not None:
        return rich_content_to_text(text)

    expression = get_object_field(value, 'expression')
    if expression:
        return str(expression)

    alternative_text = get_object_field(value, 'alternative_text')
    if alternative_text:
        return str(alternative_text)

    parts = []
    for field_name in ('summary', 'label', 'blocks', 'items', 'cells', 'caption', 'credit'):
        part = rich_content_to_text(get_object_field(value, field_name))
        if part.strip():
            parts.append(part)
    return '\n'.join(parts)

def get_message_content_text(message_like):
    if message_like is None:
        return ''

    plain_text = (
        get_object_field(message_like, 'text')
        or get_object_field(message_like, 'caption')
    )
    if plain_text:
        return str(plain_text).strip()

    rich_message = get_object_field(message_like, 'rich_message')
    if rich_message is not None:
        return rich_content_to_text(get_object_field(rich_message, 'blocks')).strip()
    return ''

def get_image_attachment(message_like):
    """Return an image attached to a Message or ExternalReplyInfo."""
    if message_like is None:
        return None

    photos = getattr(message_like, 'photo', None)
    if photos:
        return photos[-1]

    document = getattr(message_like, 'document', None)
    if (
        document is not None
        and (document.mime_type or '').casefold().startswith('image/')
    ):
        return document

    return None

def get_audio_attachment(message_like):
    """Return voice/audio attached to a Message or ExternalReplyInfo."""
    if message_like is None:
        return None

    voice = getattr(message_like, 'voice', None)
    if voice is not None:
        return voice

    audio = getattr(message_like, 'audio', None)
    if audio is not None:
        return audio

    document = getattr(message_like, 'document', None)
    if (
        document is not None
        and (document.mime_type or '').casefold().startswith('audio/')
    ):
        return document

    return None

def get_audio_format(audio):
    mime_type = (getattr(audio, 'mime_type', None) or '').casefold()
    filename = (getattr(audio, 'file_name', None) or '').casefold()
    extension = os.path.splitext(filename)[1].lstrip('.')
    if extension in {'wav', 'mp3', 'flac', 'm4a', 'ogg', 'webm', 'aac', 'aiff'}:
        return extension

    return {
        'audio/wav': 'wav',
        'audio/x-wav': 'wav',
        'audio/mpeg': 'mp3',
        'audio/mp3': 'mp3',
        'audio/flac': 'flac',
        'audio/mp4': 'm4a',
        'audio/x-m4a': 'm4a',
        'audio/ogg': 'ogg',
        'audio/webm': 'webm',
        'audio/aac': 'aac',
        'audio/aiff': 'aiff',
    }.get(mime_type, 'ogg')

def format_location(message):
    location = message.location
    details = [
        f'широта: {location.latitude}',
        f'долгота: {location.longitude}',
    ]
    if location.horizontal_accuracy is not None:
        details.append(f'точность: {location.horizontal_accuracy} м')
    if location.heading is not None:
        details.append(f'направление: {location.heading} градусов')
    if location.live_period is not None:
        details.append(f'период live location: {location.live_period} секунд')
    return 'пользователь отправил геолокацию\n' + '\n'.join(details)

def format_document_prompt(message, content):
    caption = (message.caption or '').strip()
    filename = message.document.file_name or 'без имени'
    prompt = f'пользователь отправил текстовый файл {filename}\n```text\n{content}\n```'
    if caption:
        prompt += f'\n\nподпись или вопрос пользователя\n{caption}'
    return prompt

def format_audio_prompt(transcript, question=''):
    prompt = (
        'пользователь отправил аудио\n'
        'расшифровка речи ниже считай ее словами пользователя\n'
        f'<расшифровка>{transcript}</расшифровка>'
    )
    if question.strip():
        prompt += f'\nвопрос или подпись: {question.strip()}'
    else:
        prompt += '\nответь на то что сказал пользователь'
    return prompt

def full_name(user):
    return " ".join(filter(None, (getattr(user, "first_name", None), getattr(user, "last_name", None))))
