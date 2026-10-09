from services.history import clear_history, get_chat_lock


async def start_handler(message, bot):
    await bot.reply_to(message, 'дароу')


async def clear_handler(message, bot):
    async with get_chat_lock(message.chat.id):
        clear_history(message.chat.id)
        await bot.reply_to(message, 'контекст очищен✅ вась')


def register_command_handlers(bot):
    bot.register_message_handler(start_handler,
        commands=['start'],
        pass_bot=True,
    )
    bot.register_message_handler(clear_handler,
        commands=['clear'],
        pass_bot=True,
    )
