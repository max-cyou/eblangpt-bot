import asyncio
import json
import time

import config
import prompt
from services.retry import retry_once


request_slots = asyncio.Semaphore(config.MAX_CONCURRENT_REQUESTS)


def response_text(result):
    try:
        content = result['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError('Provider response has no message') from error
    if not isinstance(content, str) or not content.strip():
        raise ValueError('Provider returned an empty answer')
    return content


async def stream_answer(query, session, history=None):
    payload = {
        'model': config.AI_MODEL,
        'messages': [
            {'role': 'system', 'content': prompt.SYSTEM_PROMPT},
            *(history or []),
            {'role': 'user', 'content': query},
        ],
        'max_tokens': config.AI_MAX_TOKENS,
        'stream': True,
    }
    headers = {'Authorization': f'Bearer {config.AI_API_KEY}'}
    async with request_slots:
        async with session.post(config.AI_API_URL, headers=headers, json=payload) as response:
            response.raise_for_status()
            if 'text/event-stream' not in response.headers.get('Content-Type', ''):
                yield response_text(await response.json())
                return
            async for raw_line in response.content:
                line = raw_line.decode('utf-8').strip()
                if not line.startswith('data:'):
                    continue
                data = line[5:].strip()
                if data in ('[DONE]', 'DONE'):
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError as error:
                    raise ValueError('Invalid provider stream') from error
                if not isinstance(event, dict) or event.get('error'):
                    raise ValueError('Provider reported a stream error')
                choices = event.get('choices') or []
                if not choices:
                    continue  # Usage-only SSE events are valid.
                try:
                    chunk = (choices[0].get('delta') or {}).get('content')
                except (AttributeError, TypeError) as error:
                    raise ValueError('Invalid provider stream event') from error
                if chunk is not None:
                    if not isinstance(chunk, str):
                        raise ValueError('Invalid stream content')
                    yield chunk


async def request_answer(query, session, history=None, update_callback=None):
    return await retry_once(lambda: _request_answer(query, session, history, update_callback))


async def _request_answer(query, session, history=None, update_callback=None):
    parts = []
    length = 0
    last_length = 0
    last_update = 0
    async for chunk in stream_answer(query, session, history):
        parts.append(chunk)
        length += len(chunk)
        now = time.monotonic()
        if update_callback and length - last_length >= 80 and now - last_update >= 0.8:
            await update_callback(''.join(parts))
            last_update, last_length = now, length
    answer = ''.join(parts).strip()
    if not answer:
        raise ValueError('Provider returned an empty answer')
    return answer
