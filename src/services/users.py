import config
from database import remember_user
from services.context import get_object_field


def remember_message_users(message):
    def remember(user, current=False):
        user_id = get_object_field(user, 'id')
        if user_id:
            remember_user(
                config.DATABASE_PATH, user_id, get_object_field(user, 'username'),
                get_object_field(user, 'is_bot', False), current,
            )

    def reference_users(reference):
        remember(get_object_field(reference, 'from_user') or get_object_field(reference, 'from'))
        remember(get_object_field(reference, 'guest_bot_caller_user'))
        remember(get_object_field(get_object_field(reference, 'origin'), 'sender_user'))

    reference_users(get_object_field(message, 'reply_to_message'))
    reference_users(get_object_field(message, 'external_reply'))
    raw = get_object_field(message, 'json') or {}
    references = get_object_field(message, 'reference_messages') or raw.get('reference_messages') or ()
    for reference in references:
        reference_users(reference)
    for user in get_object_field(message, 'new_chat_members', ()) or ():
        remember(user, current=True)
    remember(get_object_field(message, 'from_user'), current=True)
    caller = get_object_field(message, 'guest_bot_caller_user') or raw.get('guest_bot_caller_user')
    remember(caller, current=True)
