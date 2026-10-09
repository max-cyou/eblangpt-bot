async def start_handler(message, bot):
    await bot.reply_to(message, 'дароу')

def register_handlers(bot):
    bot.register_message_handler(start_handler,
        commands=['start'],
        pass_bot=True,
    )
