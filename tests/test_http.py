import unittest
from unittest.mock import patch

import aiohttp
from aiohttp import web

import config
from services.ai import request_answer


class HTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_local_http_stream_fragmentation(self):
        payloads = []
        async def handler(request):
            payloads.append(await request.json())
            response = web.StreamResponse(headers={'Content-Type': 'text/event-stream'})
            await response.prepare(request)
            stream = 'data: {"choices":[{"delta":{"content":"привет 😈 вась"}}]}\n\ndata: [DONE]\n\n'.encode()
            for offset in range(0, len(stream), 3):
                await response.write(stream[offset:offset + 3])
            await response.write_eof()
            return response
        app = web.Application()
        app.router.add_post('/chat/completions', handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            with patch.object(config, 'AI_API_URL', f'http://127.0.0.1:{port}/chat/completions'):
                async with aiohttp.ClientSession() as session:
                    answer = await request_answer('hello', session, [{'role': 'user', 'content': 'past'}])
            self.assertEqual(answer, 'привет 😈 вась')
            self.assertTrue(payloads[0]['stream'])
            self.assertEqual(payloads[0]['messages'][1]['content'], 'past')
        finally:
            await runner.cleanup()
