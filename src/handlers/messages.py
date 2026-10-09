from services.ai import generate_answer


async def message_handler(message, bot):
    answer = await generate_answer(message.text)
    await bot.reply_to(message, answer)

def register_message_handlers(bot):
    bot.register_message_handler(message_handler,
        content_types=['text'],
        pass_bot=True,
    )
