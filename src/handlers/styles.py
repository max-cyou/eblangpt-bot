from telebot import types

from services.chats import remember_message
from services.styles import get_user_style, set_user_style
from services.telegram import edit_text, telegram_call
from styles import STYLES


def style_menu(user_id):
    selected = get_user_style(user_id)
    keyboard = types.InlineKeyboardMarkup()
    for style in STYLES.values():
        label = f'✅ {style.name}' if style.id == selected.id else style.name
        keyboard.row(types.InlineKeyboardButton(label, callback_data=f'style:{user_id}:{style.id}'))
    text = (
        f'слыш😈 сейчас базарю так: {selected.name}\n{selected.description}\n\n'
        'выбирай стиль снизу💪 работает в личке группах и guest\n'
        'память на месте вась — стереть можно через /clear\n\n'
        'хочешь свой стиль👍 закидывай через пулл реквест:\n'
        'https://github.com/max-cyou/eblangpt-bot/blob/main/CONTRIBUTING.md'
    )
    return text, keyboard


def register_style_handlers(bot):
    async def style_command(message):
        if not message.from_user:
            return
        remember_message(message)
        text, keyboard = style_menu(message.from_user.id)
        await telegram_call(
            bot.send_message, chat_id=message.chat.id, text=text,
            message_thread_id=message.message_thread_id, reply_markup=keyboard,
            parse_mode=None,
        )

    async def select_style(call):
        parts = (call.data or '').split(':')
        if len(parts) != 3 or not parts[1].isdigit():
            await telegram_call(bot.answer_callback_query, callback_query_id=call.id, text='кнопка сломалась😈 открой /style заново вась')
            return
        if int(parts[1]) != call.from_user.id:
            await telegram_call(
                bot.answer_callback_query, callback_query_id=call.id,
                text='вась😈 это чужое меню💪 свое открывай через /style', show_alert=True,
            )
            return
        if parts[2] not in STYLES:
            await telegram_call(bot.answer_callback_query, callback_query_id=call.id, text='этот стиль убрали😈 открой /style и выбери другой вась')
            return
        style = set_user_style(call.from_user.id, parts[2])
        await telegram_call(bot.answer_callback_query, callback_query_id=call.id, text=f'стиль поменял✅ теперь {style.name} вась')
        if call.message:
            text, keyboard = style_menu(call.from_user.id)
            await edit_text(
                bot, text, chat_id=call.message.chat.id,
                message_id=call.message.message_id, reply_markup=keyboard,
            )

    bot.register_message_handler(style_command, commands=['style'])
    bot.register_callback_query_handler(select_style, func=lambda call: (call.data or '').startswith('style:'))
