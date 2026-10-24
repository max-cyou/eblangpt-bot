import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch
import config

from handlers.commands import register_command_handlers
from handlers.groups import register_group_handlers
from handlers.messages import register_message_handlers
from services.ai import filter_answer_artifacts, request_answer
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
        self.assertIn('текст: first\n', messages[1]['content'])
        self.assertIn('имя: Offline\n', messages[1]['content'])
        self.assertIn('username: @offline\n', messages[1]['content'])
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
        self.assertEqual(len(self.session.calls), 6)

    async def test_retry_success_saved_once_without_fallback(self):
        self.session.responses = [Response(status=503), Response()]
        await self.bot.process_new_messages([make_message('retry')])
        self.assertEqual(len(self.session.calls), 2)
        self.assertEqual(len(get_history(1)), 2)
        self.assertEqual(get_history(1)[-1]['content'], self.bot.send_rich_message.call_args.kwargs['rich_message'].markdown)

    async def test_reply_text_in_private_prompt(self):
        await self.bot.process_new_messages([make_message('поясни', reply_to_message=make_message('reference text').json)])
        self.assertIn('reference text', self.session.calls[-1][1]['json']['messages'][-1]['content'])

    async def test_private_names_and_username_changes_in_history(self):
        sender = {'id': 42, 'is_bot': False, 'first_name': 'Макс', 'last_name': 'Тест', 'username': 'max_test'}
        await self.bot.process_new_messages([make_message('первое', **{'from': sender})])
        sender = dict(sender, username=None)
        await self.bot.process_new_messages([make_message('второе', **{'from': sender})])
        messages = self.session.calls[-1][1]['json']['messages']
        self.assertIn('имя: Макс Тест\n', messages[1]['content'])
        self.assertIn('username: @max_test\n', messages[1]['content'])
        self.assertIn('имя: Макс Тест\n', messages[-1]['content'])
        self.assertIn('username: нет\n', messages[-1]['content'])
        self.assertIn('упоминание: [Макс Тест](tg://user?id=42)', messages[-1]['content'])

    async def test_private_reply_keeps_both_authors(self):
        reference = make_message('original', **{'from': {
            'id': 50, 'is_bot': False, 'first_name': 'Друг', 'username': 'friend',
        }})
        await self.bot.process_new_messages([make_message('поясни', reply_to_message=reference.json)])
        text = self.session.calls[-1][1]['json']['messages'][-1]['content']
        self.assertIn('имя: Offline\n', text)
        self.assertIn('username: @offline\n', text)
        self.assertIn('имя: Друг\n', text)
        self.assertIn('username: @friend\n', text)

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
    async def test_extra_marker_removes_duplicate_with_emoji_spacing_changes(self):
        first = 'слыш 😈 модель опять повторила целый ответ вась 💪 бывает 😂😂'
        second = first.replace(' 😂😂', '😂')
        text = first + '</extra?' + second + '</extra?>'
        response = Response({'choices': [{'message': {'content': text}}]})
        self.assertEqual(await request_answer('test', Session([response])), first)
        self.assertEqual(filter_answer_artifacts('ответ</extra?> другой текст'), 'ответ другой текст')

    async def test_extra_marker_split_in_stream_does_not_publish_duplicate(self):
        answer = 'готовый осмысленный ответ 😈 ' * 4
        for marker in ('</extra?', '</extra?>'):
            for split in range(1, len(marker)):
                chunks = [answer + marker[:split], marker[split:] + answer[:20], answer[20:]]
                response = Response(lines=[
                    'data: ' + json.dumps({'choices': [{'delta': {'content': chunk}}]}) for chunk in chunks
                ] + ['data: [DONE]'])
                update = AsyncMock()
                self.assertEqual(await request_answer('test', Session([response]), update_callback=update), answer.strip())
                for call in update.await_args_list:
                    self.assertEqual(call.args[0].strip(), answer.strip())

    async def test_json_answer_removes_all_markers_and_preserves_surrounding_text(self):
        for marker in ('</формирую_ответ>', '</формируя_ответ>', '</ФОРМИРУЮ_ОТВЕТ>'):
            response = Response({'choices': [{'message': {'content': 'ответ 😈 вась ' + marker + 'correctCorrect' * 100 + marker + ' конец'}}]})
            self.assertEqual(await request_answer('test', Session([response])), 'ответ 😈 вась ' + 'correctCorrect' * 100 + ' конец')

    async def test_split_marker_never_reaches_stream_updates(self):
        answer = 'готовый ответ ' * 10
        for marker in ('</формирую_ответ>', '</формируя_ответ>'):
            for split in range(1, len(marker)):
                tail = 'Correct' * 100
                chunks = [answer + marker[:split], marker[split:] + tail, ' продолжение']
                lines = ['data: ' + json.dumps({'choices': [{'delta': {'content': chunk}}]}) for chunk in chunks]
                lines.append('data: [DONE]')
                response = Response(lines=lines)
                update = AsyncMock()
                with patch.object(Response, '__aexit__', new_callable=AsyncMock) as close:
                    self.assertEqual(await request_answer('test', Session([response]), update_callback=update), answer + tail + ' продолжение')
                    close.assert_awaited_once()
                self.assertTrue(update.await_count)
                for call in update.await_args_list:
                    self.assertNotIn('<', call.args[0])
                    self.assertNotIn('формир', call.args[0])
                    self.assertTrue((answer + tail + ' продолжение').startswith(call.args[0]))

    async def test_old_assistant_artifacts_are_not_sent_back_to_model(self):
        history = [
            {'role': 'user', 'content': 'что значит </формирую_ответ>Correct'},
            {'role': 'assistant', 'content': 'старый ответ </формирую_ответ>CorrectCorrect'},
        ]
        session = Session()
        await request_answer('test', session, history)
        messages = session.calls[0][1]['json']['messages']
        self.assertEqual(messages[1], history[0])
        self.assertEqual(messages[2]['content'], 'старый ответ CorrectCorrect')
        self.assertIn('CorrectCorrect', history[1]['content'])

    async def test_normal_code_markup_and_correct_are_preserved(self):
        answer = '<u>correct</u>\n```python\nprint("CorrectCorrect")\n```\nß <'
        response = Response({'choices': [{'message': {'content': answer}}]})
        self.assertEqual(await request_answer('test', Session([response])), answer)

    async def test_marker_without_answer_retries(self):
        response = Response({'choices': [{'message': {'content': '</формирую_ответ></формируя_ответ>'}}]})
        session = Session([response, Response()])
        self.assertEqual(await request_answer('test', session), 'offline answer')
        self.assertEqual(len(session.calls), 2)

    async def test_reasoning_effort_is_configurable(self):
        for effort in ('none', ''):
            session = Session()
            with patch.object(config, 'AI_REASONING_EFFORT', effort):
                await request_answer('test', session)
            payload = session.calls[0][1]['json']
            if effort:
                self.assertEqual(payload['reasoning_effort'], effort)
            else:
                self.assertNotIn('reasoning_effort', payload)

    async def test_retry_discards_partial_failed_stream(self):
        first = Response(lines=[
            'data: {"choices":[{"delta":{"content":"discard this "}}]}\n',
            'data: {"error":"unavailable"}\n',
        ])
        session = Session([first, Response()])
        self.assertEqual(await request_answer('test', session), 'offline answer')
        self.assertEqual(len(session.calls), 2)

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
