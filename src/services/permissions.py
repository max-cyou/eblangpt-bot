import config
from services.context import get_object_field


def is_admin(message):
    return is_admin_user(message.from_user)


def is_admin_user(sender):
    if not sender:
        return False
    if config.ADMIN_USER_ID:
        return get_object_field(sender, 'id') == config.ADMIN_USER_ID
    username = get_object_field(sender, 'username')
    return bool(config.ADMIN_USERNAME and username and username.casefold() == config.ADMIN_USERNAME)
