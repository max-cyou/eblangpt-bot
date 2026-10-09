import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from handlers.commands import register_command_handlers
from handlers.groups import register_group_handlers
from handlers.messages import register_message_handlers
from services.ai import request_answer
from services.chats import bot_users
from services.history import get_history
from tests.helpers import BotTestMixin, Response, Session, make_message


class MessageTests(BotTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        register_command_handlers(self.bot)
        register_message_handlers(self.bot, self.session)
        register_group_handlers(self.bot, self.session)

    async def test_private_history_and_clear(self):
        await self.bot.process_new_messages([make_message('first')])
        await self.bot.process_new_messages([make_message('second')])
        messages = self.session.calls[-1][1]['json']['messages']
        self.assertEqual([m['role'] for m in messages], ['system', 'user', 'assistant', 'user'])
        self.assertEqual(messages[1]['content'], 'first')
        await self.bot.process_new_messages([make_message('/clear')])
        self.assertEqual(get_history(1), [])
        self.assertEqual(len(self.session.calls), 2)

    async def test_group_passive_and_explicit_triggers(self):
        await self.bot.process_new_messages([make_message('пассивный текст', -1, 'supergroup')])
        self.assertEqual(len(self.session.calls), 0)
        self.assertIn('пассивный текст', get_history(-1)[0]['content'])
        for trigger in ('ВАСЬ привет', '@offlinebot привет'):
            await self.bot.process_new_messages([make_message(trigger, -1, 'supergroup')])
        self.assertEqual(len(self.session.calls), 2)
        self.assertIn('telegram_id: 42', self.session.calls[-1][1]['json']['messages'][-1]['content'])
        reply = make_message('bot answer').json
        reply['from']['id'] = 999
        await self.bot.process_new_messages([make_message('ответ', -2, 'group', reply_to_message=reply)])
        self.assertEqual(len(self.session.calls), 3)

    async def test_timeout_and_http_never_enter_history(self):
        for failure in (asyncio.TimeoutError(), Response(status=429), Response(result={'error': 'bad response'})):
            self.session.responses = [failure]
            await self.bot.process_new_messages([make_message('fail')])
            self.assertEqual(get_history(1), [])
        self.assertEqual(self.bot.send_rich_message.await_count, 3)

    async def test_reply_text_in_private_prompt(self):
        await self.bot.process_new_messages([make_message('поясни', reply_to_message=make_message('reference text').json)])
        self.assertIn('reference text', self.session.calls[-1][1]['json']['messages'][-1]['content'])

    async def test_clear_waits_for_generation(self):
        entered, release = asyncio.Event(), asyncio.Event()
        response = Response()

        async def delayed_json():
            entered.set()
            await release.wait()
            return {'choices': [{'message': {'content': 'delayed answer'}}]}

        response.json = delayed_json
        self.session.responses = [response]
        generation = asyncio.create_task(self.bot.process_new_messages([make_message('slow')]))
        await entered.wait()
        clearing = asyncio.create_task(self.bot.process_new_messages([make_message('/clear')]))
        await asyncio.sleep(0)
        self.assertFalse(clearing.done())
        release.set()
        await asyncio.gather(generation, clearing)
        self.assertEqual(get_history(1), [])


class StreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_sse_and_json_compatibility(self):
        response = Response(lines=[
            'data: {"choices":[{"delta":{"content":"привет "}}]}\n',
            'data: {"choices":[],"usage":{}}\n',
            'data: {"choices":[{"delta":{"content":"вась"}}]}\n',
            'data: [DONE]\n',
        ])
        self.assertEqual(await request_answer('test', Session([response])), 'привет вась')
        self.assertEqual(await request_answer('test', Session()), 'offline answer')

    async def test_invalid_and_empty_streams_fail(self):
        for lines in (['data: {broken}\n'], ['data: {"error":"unavailable"}\n'], ['data: [DONE]\n']):
            with self.assertRaises(ValueError):
                await request_answer('test', Session([Response(lines=lines)]))
