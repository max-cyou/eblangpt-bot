import config
from database import mark_chat_inactive, remember_chat
from services.chats import get_bot_user, remember_message
from services.history import clear_history, get_chat_lock, save_exchange
from services.telegram import send_text
from handlers.commands import send_picture_or_text


async def greet_group(message, bot):
    remember_message(message)
    current = await get_bot_user(bot)
    if any(member.id == current.id for member in message.new_chat_members):
        greeting = 'салам👍 васьки✅ я eblangpt созданный maxcyou✅ подписываемся @maxcyou'
        async with get_chat_lock(message.chat.id, message.message_thread_id):
            clear_history(message.chat.id, message.message_thread_id)
            # Save as a user/assistant exchange so history starts with a user turn.
            save_exchange(message.chat.id, 'бот добавлен в группу', greeting, message.message_thread_id)
        await send_picture_or_text(bot, message, config.GROUP_WELCOME_IMAGE_PATH, greeting)
        return
    for index, _ in enumerate(message.new_chat_members):
        text = 'э✅ вась👍 ты кто👍 кого вы добавили пацаны✅'
        if index:
            text += f' уже {index}✅'
        await send_text(bot, message, text)


async def farewell(message, bot):
    remember_message(message)
    if message.left_chat_member.id != (await get_bot_user(bot)).id:
        await send_text(bot, message, 'ну и пошел😈 нахуй')
    else:
        mark_chat_inactive(config.DATABASE_PATH, message.chat.id)


async def membership_changed(update, bot):
    chat = update.chat
    if update.new_chat_member.status in ('left', 'kicked'):
        mark_chat_inactive(config.DATABASE_PATH, chat.id)
    else:
        remember_chat(config.DATABASE_PATH, chat.id, chat.type, chat.username, chat.title)


def register_event_handlers(bot):
    bot.register_message_handler(greet_group, content_types=['new_chat_members'], pass_bot=True)
    bot.register_message_handler(farewell, content_types=['left_chat_member'], pass_bot=True)
    bot.register_my_chat_member_handler(membership_changed, pass_bot=True)
