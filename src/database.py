import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


_db_lock = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def initialize_database(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with _db_lock, closing(sqlite3.connect(path)) as connection:
        connection.execute('PRAGMA journal_mode=WAL')
        with connection:
            connection.executescript(
                '''
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                chat_type TEXT NOT NULL,
                username TEXT,
                title TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS counters (
                name TEXT PRIMARY KEY,
                value INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                style_id TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS group_random_reply_state (
                chat_id INTEGER PRIMARY KEY,
                messages_left INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                thread_id INTEGER NOT NULL DEFAULT 0,
                role TEXT NOT NULL,
                content TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS history_chat
                ON history(chat_id, thread_id, id);
                '''
            )
    # The database stores chat messages and should be private to its owner.
    Path(path).chmod(0o600)


def remember_chat(path, chat_id, chat_type, username=None, title=None):
    timestamp = _now()
    with _db_lock, closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.execute(
                '''
            INSERT INTO chats (
                chat_id, chat_type, username, title, active, first_seen, last_seen
            ) VALUES (?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                chat_type = excluded.chat_type,
                username = excluded.username,
                title = excluded.title,
                active = 1,
                last_seen = excluded.last_seen
                ''',
                (chat_id, chat_type, username, title, timestamp, timestamp),
            )


def mark_chat_inactive(path, chat_id):
    with _db_lock, closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.execute(
                'UPDATE chats SET active = 0, last_seen = ? WHERE chat_id = ?',
                (_now(), chat_id),
            )


def increment_counter(path, name, amount=1):
    with _db_lock, closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.execute(
                '''
            INSERT INTO counters (name, value) VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET value = value + excluded.value
                ''',
                (name, amount),
            )


def consume_group_random_reply(path, chat_id, next_interval):
    """Count a group message and return True when a random reply is due."""
    if next_interval < 1:
        raise ValueError('next_interval must be positive')

    with _db_lock, closing(sqlite3.connect(path)) as connection:
        with connection:
            row = connection.execute(
                'SELECT messages_left FROM group_random_reply_state WHERE chat_id = ?',
                (chat_id,),
            ).fetchone()
            messages_left = row[0] if row is not None else next_interval
            messages_left -= 1
            reply_due = messages_left <= 0
            if reply_due:
                messages_left = next_interval

            connection.execute(
                '''
            INSERT INTO group_random_reply_state (chat_id, messages_left)
            VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                messages_left = excluded.messages_left
                ''',
                (chat_id, messages_left),
            )
    return reply_due


def get_private_recipient_ids(path):
    with _db_lock, closing(sqlite3.connect(path)) as connection:
        rows = connection.execute(
            '''
            SELECT chat_id
            FROM chats
            WHERE chat_type = 'private' AND active = 1
            ORDER BY first_seen
            '''
        ).fetchall()
    return [row[0] for row in rows]


def get_statistics(path):
    with _db_lock, closing(sqlite3.connect(path)) as connection:
        counts = dict(connection.execute('SELECT name, value FROM counters'))
        private_users = connection.execute(
            "SELECT COUNT(*) FROM chats WHERE chat_type = 'private'"
        ).fetchone()[0]
        active_private_users = connection.execute(
            "SELECT COUNT(*) FROM chats WHERE chat_type = 'private' AND active = 1"
        ).fetchone()[0]
        groups = connection.execute(
            "SELECT COUNT(*) FROM chats WHERE chat_type IN ('group', 'supergroup')"
        ).fetchone()[0]

    return {
        **counts,
        'private_users': private_users,
        'active_private_users': active_private_users,
        'groups': groups,
    }


def read_history(path, chat_id, thread_id=0):
    with _db_lock, closing(sqlite3.connect(path)) as connection:
        rows = connection.execute(
            'SELECT role, content FROM history WHERE chat_id = ? AND thread_id = ? ORDER BY id',
            (chat_id, thread_id),
        ).fetchall()
    return [{'role': role, 'content': content} for role, content in rows]


def append_history(path, chat_id, thread_id, items, message_limit, char_limit):
    """Persist and trim atomically; keep the newest exchange even for large inputs."""
    with _db_lock, closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.executemany(
                'INSERT INTO history(chat_id, thread_id, role, content) VALUES (?, ?, ?, ?)',
                [(chat_id, thread_id, item['role'], item['content']) for item in items],
            )
            rows = connection.execute(
                'SELECT id, role, content FROM history WHERE chat_id = ? AND thread_id = ? ORDER BY id',
                (chat_id, thread_id),
            ).fetchall()
            while len(rows) > message_limit:
                rows.pop(0)
            while rows and rows[0][1] == 'assistant':
                rows.pop(0)
            total = sum(len(row[2]) for row in rows)
            # Remove complete old exchanges, never the newest question and answer.
            while total > char_limit and len(rows) > max(2, len(items)):
                total -= len(rows.pop(0)[2])
                while rows and rows[0][1] == 'assistant':
                    total -= len(rows.pop(0)[2])
            if total > char_limit:
                # Allocate space to both sides instead of dropping a large exchange.
                remaining = char_limit
                for index, (row_id, role, content) in enumerate(rows):
                    budget = remaining // (len(rows) - index)
                    content = content[-budget:] if budget else ''
                    remaining -= len(content)
                    rows[index] = row_id, role, content
                    connection.execute('UPDATE history SET content = ? WHERE id = ?', (content, row_id))
            if rows:
                connection.execute(
                    'DELETE FROM history WHERE chat_id = ? AND thread_id = ? AND id < ?',
                    (chat_id, thread_id, rows[0][0]),
                )
            else:
                connection.execute('DELETE FROM history WHERE chat_id = ? AND thread_id = ?', (chat_id, thread_id))


def delete_history(path, chat_id, thread_id=0):
    with _db_lock, closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.execute('DELETE FROM history WHERE chat_id = ? AND thread_id = ?', (chat_id, thread_id))


def get_user_style_id(path, user_id):
    with _db_lock, closing(sqlite3.connect(path)) as connection:
        row = connection.execute('SELECT style_id FROM user_settings WHERE user_id = ?', (user_id,)).fetchone()
    return row[0] if row else None


def set_user_style_id(path, user_id, style_id):
    with _db_lock, closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.execute(
                '''INSERT INTO user_settings(user_id, style_id) VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET style_id = excluded.style_id''',
                (user_id, style_id),
            )
