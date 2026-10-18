from telebot import util
from telebot.asyncio_handler_backends import BaseMiddleware, CancelUpdate

from services.bans import ban_reply, message_group_is_banned, message_is_banned
from services.chats import get_bot_user, remember_message
from services.permissions import is_admin
from services.telegram import send_text
from services.users import remember_message_users


class AdminMiddleware(BaseMiddleware):
    update_types = ['message']
    denial_messages = {
        'stats': 'тебе нельзя😈 статистика не твоя вась',
        'broadcast': 'иди гуляй😈 рассылка только для админа',
    }

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def pre_process(self, message, data):
        if message.content_type != 'text':
            return
        command = util.extract_command(message.text)
        if command not in self.denial_messages or is_admin(message):
            return
        # Middleware runs before the existing group/user ban handlers.
        # Preserve their silence/refusal behavior for these commands.
        if message_group_is_banned(message):
            return CancelUpdate()
        remember_message_users(message)
        if message_is_banned(message):
            target = message.text.split()[0].partition('@')[2]
            if target and message.chat.type != 'private':
                current = await get_bot_user(self.bot)
                if target.casefold() != (current.username or '').casefold():
                    return CancelUpdate()
            await send_text(self.bot, message, ban_reply())
        else:
            remember_message(message)
            await send_text(self.bot, message, self.denial_messages[command])
        return CancelUpdate()

    async def post_process(self, message, data, exception):
        pass
