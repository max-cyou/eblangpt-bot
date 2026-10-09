import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import config
from database import initialize_database
from services.history import clear_history, get_history, save_exchange


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'history.sqlite3'
        self.settings = patch.multiple(config, DATABASE_PATH=self.path, HISTORY_LIMIT=10, CONTEXT_CHAR_LIMIT=100)
        self.settings.start()
        initialize_database(self.path)

    def tearDown(self):
        self.settings.stop()
        self.directory.cleanup()

    def test_survives_another_process_and_clear(self):
        save_exchange(1, 'question', 'answer')
        env = {**os.environ, 'DATABASE_PATH': str(self.path), 'PYTHONPATH': str(config.PROJECT_ROOT / 'src')}
        result = subprocess.check_output(
            [sys.executable, '-c', 'import json; from services.history import get_history; print(json.dumps(get_history(1)))'],
            env=env, text=True,
        )
        self.assertEqual(json.loads(result), get_history(1))
        clear_history(1)
        self.assertEqual(get_history(1), [])

    def test_chat_and_topic_isolation_and_copy(self):
        save_exchange(1, 'first', 'answer', 10)
        save_exchange(1, 'second', 'answer', 20)
        save_exchange(2, 'other', 'answer')
        copy = get_history(1, 10)
        copy[0]['content'] = 'changed'
        clear_history(1, 20)
        self.assertEqual(get_history(1, 10)[0]['content'], 'first')
        self.assertEqual(get_history(1, 20), [])
        self.assertEqual(get_history(2)[0]['content'], 'other')

    def test_limits_preserve_newest_exchange(self):
        for index in range(9):
            save_exchange(1, str(index), 'answer')
        self.assertEqual(len(get_history(1)), 10)
        save_exchange(1, 'q' * 1000, 'a' * 1000)
        history = get_history(1)
        self.assertEqual([item['role'] for item in history], ['user', 'assistant'])
        self.assertLessEqual(sum(len(item['content']) for item in history), 100)
        self.assertTrue(all(item['content'] for item in history))
