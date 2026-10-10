import base64
import binascii
import hashlib
import re
import struct

import config
from database import (
    find_guest_response_style, get_message_style_binding, get_user_style_id,
    pin_message_style, remember_guest_response_style,
)
from services.context import get_message_content_text, get_object_field
from styles import get_style


def _user_style(user_id):
    return get_style(get_user_style_id(config.DATABASE_PATH, user_id) if user_id is not None else None)


def guest_response_scope(message):
    if message.guest_query_id and message.chat.type == 'private':
        # A guest private chat is between two people, not between a person and this bot.
        ids = sorted((message.chat.id, getattr(message.from_user, 'id', 0)))
        return f'guest-private:{ids[0]}:{ids[1]}'
    return f'chat:{message.chat.id}'


def style_scope(message):
    scope = guest_response_scope(message)
    if message.guest_query_id and message.chat.type == 'private':
        # Private message IDs belong to the receiving user's view of the chat.
        scope += f':viewer:{getattr(message.from_user, "id", 0)}'
    return scope


def guest_content_hash(text):
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'[`*_~\s]', '', text)
    return hashlib.sha256(text.encode()).hexdigest()


def reference_in_chat(message, reference):
    if message.chat.type == 'private' and not message.guest_query_id and get_object_field(reference, 'guest_bot_caller_user'):
        return False
    chat = get_object_field(reference, 'chat')
    if not chat:
        return True
    if message.guest_query_id and message.chat.type == 'private':
        participants = {message.chat.id, getattr(message.from_user, 'id', 0)}
        caller = get_object_field(reference, 'guest_bot_caller_user')
        sender = caller or get_object_field(reference, 'from_user') or get_object_field(reference, 'from')
        if sender and not get_object_field(sender, 'is_bot', False) and get_object_field(sender, 'id') not in participants:
            return False
        return get_object_field(chat, 'id') in participants
    return get_object_field(chat, 'id') == message.chat.id


def get_message_style(message, references=None):
    scope = style_scope(message)
    binding = get_message_style_binding(config.DATABASE_PATH, scope, message.message_id)
    if binding:
        return get_style(binding[1])
    references = references if references is not None else [message.reply_to_message]
    references = [reference for reference in references if reference and reference_in_chat(message, reference)]
    # Prefer the explicit reply, then any supplied ancestors already seen by the bot.
    for reference in references:
        caller = get_object_field(reference, 'guest_bot_caller_user')
        text = get_message_content_text(reference)
        if caller and text:
            binding = find_guest_response_style(
                config.DATABASE_PATH, guest_response_scope(message),
                get_object_field(caller, 'id'), guest_content_hash(text),
            )
            if binding:
                break
        reference_id = get_object_field(reference, 'message_id')
        if reference_id:
            binding = get_message_style_binding(config.DATABASE_PATH, scope, reference_id)
            if binding:
                break
    topic_id = message.message_thread_id if message.is_topic_message else None
    if not binding and topic_id:
        binding = get_message_style_binding(config.DATABASE_PATH, scope, topic_id)
    if not binding and references:
        reference = references[0]
        sender = get_object_field(reference, 'guest_bot_caller_user') or get_object_field(reference, 'from_user') or get_object_field(reference, 'from')
        if sender and not get_object_field(sender, 'is_bot', False):
            owner_id = get_object_field(sender, 'id')
            style = _user_style(owner_id)
            binding = (owner_id, style.id)
            reference_id = get_object_field(reference, 'message_id')
            if reference_id:
                binding = pin_message_style(config.DATABASE_PATH, scope, reference_id, *binding)
    if not binding:
        owner_id = getattr(message.from_user, 'id', None)
        binding = (owner_id, _user_style(owner_id).id)
    if topic_id:
        binding = pin_message_style(config.DATABASE_PATH, scope, topic_id, *binding)
    binding = pin_message_style(config.DATABASE_PATH, scope, message.message_id, *binding)
    return get_style(binding[1])


def remember_reply_style(message, sent):
    message_id = getattr(sent, 'message_id', None)
    if not message_id:
        return
    scope = style_scope(message)
    binding = get_message_style_binding(config.DATABASE_PATH, scope, message.message_id)
    if binding:
        pin_message_style(config.DATABASE_PATH, scope, message_id, *binding)


def guest_reply_message_id(inline_message_id):
    """Read the message ID from Telegram's base64url-encoded inline identifier.

    Layouts: https://core.telegram.org/type/InputBotInlineMessageID
    Encoding: https://github.com/tdlib/td/blob/master/td/telegram/InlineQueriesManager.cpp
    Unknown layouts deliberately return None instead of inventing an ID.
    """
    try:
        data = base64.b64decode(inline_message_id + '=' * (-len(inline_message_id) % 4), altchars=b'-_', validate=True)
        if len(data) in (24, 28):
            constructor = int.from_bytes(data[:4], 'little')
            if constructor in (0x890C3D89, 0xB6D915D7):
                data = data[4:]
        if len(data) == 24:
            dc_id, _, message_id, _ = struct.unpack('<iqiq', data)
        elif len(data) == 20:
            dc_id, packed_id, _ = struct.unpack('<iqq', data)
            message_id = packed_id & 0xFFFFFFFF
        else:
            return None
        return message_id if dc_id > 0 and 0 < message_id < 2**31 else None
    except (ValueError, TypeError, binascii.Error, struct.error):
        return None


def remember_guest_reply_style(message, inline_message_id):
    message_id = guest_reply_message_id(inline_message_id)
    if message_id:
        scope = style_scope(message)
        binding = get_message_style_binding(config.DATABASE_PATH, scope, message.message_id)
        if binding:
            pin_message_style(config.DATABASE_PATH, scope, message_id, *binding)


def remember_guest_reply_text(message, text):
    binding = get_message_style_binding(config.DATABASE_PATH, style_scope(message), message.message_id)
    if binding and message.from_user and text:
        remember_guest_response_style(
            config.DATABASE_PATH, guest_response_scope(message), message.from_user.id,
            guest_content_hash(text), *binding,
        )
