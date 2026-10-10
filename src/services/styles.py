import config
from database import get_user_style_id, set_user_style_id
from styles import STYLES, get_style
from services.emojis import add_emojis_to_casual_answer


def get_user_style(user_id):
    if user_id is None:
        return get_style()
    return get_style(get_user_style_id(config.DATABASE_PATH, user_id))


def set_user_style(user_id, style_id):
    if style_id not in STYLES:
        raise ValueError('Unknown style')
    set_user_style_id(config.DATABASE_PATH, user_id, style_id)
    return STYLES[style_id]


def get_message_style(message):
    return get_user_style(getattr(getattr(message, 'from_user', None), 'id', None))


def format_style_answer(answer, history, style):
    return add_emojis_to_casual_answer(answer, history) if style.auto_emojis else answer


def style_status_text(style, kind='ai'):
    defaults = {'ai': 'Готовлю ответ…', 'image': 'Распознаю изображение…', 'audio': 'Распознаю речь…'}
    return style.statuses.get(kind, defaults.get(kind, defaults['ai']))
