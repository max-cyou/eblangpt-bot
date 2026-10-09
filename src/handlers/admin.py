import asyncio
import logging
import re

from telebot import types
from telebot.asyncio_helper import ApiException, ApiTelegramException

import config
from database import get_private_recipient_ids, get_statistics, increment_counter, mark_chat_inactive
from services.chats import remember_message
from services.errors import failure_details
from services.telegram import send_text, telegram_call, text_chunks


logger = logging.getLogger(__name__)
broadcast_lock = asyncio.Lock()


def is_admin(message):
    sender = message.from_user
    if not sender:
        return False
    if config.ADMIN_USER_ID:
        return sender.id == config.ADMIN_USER_ID
    return bool(config.ADMIN_USERNAME and sender.username and sender.username.casefold() == config.ADMIN_USERNAME)


def extract_broadcast_text(message):
    return re.sub(r'^\s*/broadcast(?:@[A-Za-z0-9_]+)?(?=\s|$)', '', message.text or '', count=1, flags=re.I).strip()


async def broadcast_item(bot, chat_id, message, text):
    if message.reply_to_message:
        await telegram_call(bot.copy_message, chat_id=chat_id, from_chat_id=message.chat.id,
                            message_id=message.reply_to_message.message_id)
        return
    for chunk in text_chunks(text):
        try:
            await telegram_call(bot.send_rich_message, chat_id=chat_id,
                                rich_message=types.InputRichMessage(markdown=chunk))
        except ApiTelegramException as error:
            if error.error_code != 400:
                raise
            await telegram_call(bot.send_message, chat_id=chat_id, text=chunk, parse_mode=None)


async def stats_handler(message, bot):
    remember_message(message)
    if not is_admin(message):
        await send_text(bot, message, 'тебе нельзя😈 статистика не твоя вась')
        return
    stats = get_statistics(config.DATABASE_PATH)
    fields = (
        ('пользователей', 'private_users'), ('активных для рассылки', 'active_private_users'),
        ('групп', 'groups'), ('случайных ответов в группах', 'group_random_replies'),
        ('генераций', 'generations'), ('ошибок ии', 'ai_errors'), ('guest запросов', 'guest_requests'),
        ('распознано изображений', 'images_recognized'), ('ошибок изображений', 'image_errors'),
        ('распознано аудио', 'audio_transcriptions'), ('ошибок аудио', 'audio_errors'),
        ('текстовых файлов', 'text_files'), ('геолокаций', 'locations'),
        ('рассылок', 'broadcasts'), ('доставлено в рассылках', 'broadcast_deliveries'),
    )
    text = '**статистика eblangpt**\n\n' + '\n'.join(f'{title}: {stats.get(key, 0)}' for title, key in fields)
    await send_text(bot, message, text)


async def broadcast_handler(message, bot):
    remember_message(message)
    if not is_admin(message):
        await send_text(bot, message, 'иди гуляй😈 рассылка только для админа')
        return
    if message.chat.type != 'private':
        await send_text(bot, message, 'рассылку запускай в лс👍')
        return
    text = extract_broadcast_text(message)
    if not text and not message.reply_to_message:
        await send_text(bot, message, 'напиши `/broadcast текст` или ответь командой на готовое сообщение')
        return
    if broadcast_lock.locked():
        await send_text(bot, message, 'вась😈 одна рассылка уже идет💪 дождись ее')
        return
    async with broadcast_lock:
        recipients = get_private_recipient_ids(config.DATABASE_PATH)
        delivered = failed = 0
        status = await bot.send_message(message.chat.id, f'бжжж💪 начинаю рассылку для {len(recipients)} челов')
        for chat_id in recipients:
            try:
                await broadcast_item(bot, chat_id, message, text)
            except ApiTelegramException as error:
                if error.error_code == 403 or (error.error_code == 400 and 'chat not found' in error.description.casefold()):
                    mark_chat_inactive(config.DATABASE_PATH, chat_id)
                failed += 1
                logger.warning('Broadcast delivery failed: %s', failure_details(error))
            except ApiException as error:
                failed += 1
                logger.warning('Broadcast delivery failed: %s', failure_details(error))
            else:
                delivered += 1
            await asyncio.sleep(0.04)
        increment_counter(config.DATABASE_PATH, 'broadcasts')
        increment_counter(config.DATABASE_PATH, 'broadcast_deliveries', delivered)
        await bot.edit_message_text(
            f'рассылка готова✅ доставлено {delivered} ошибок {failed}',
            chat_id=message.chat.id, message_id=status.message_id,
        )


def register_admin_handlers(bot):
    bot.register_message_handler(stats_handler, commands=['stats'], pass_bot=True)
    bot.register_message_handler(broadcast_handler, commands=['broadcast'], pass_bot=True)
