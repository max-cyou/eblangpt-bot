async def message_handler(message, bot):
    await bot.reply_to(message, message.text)

def register_message_handlers(bot):
    bot.register_message_handler(message_handler,
        content_types=['text'],
        pass_bot=True,
    )
