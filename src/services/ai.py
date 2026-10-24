import asyncio
import json
import re
import time
from contextlib import aclosing
from difflib import SequenceMatcher

import config
from styles import get_style
from services.retry import retry_once


request_slots = asyncio.Semaphore(config.MAX_CONCURRENT_REQUESTS)
ANSWER_END_ARTIFACTS = ('</формирую_ответ>', '</формируя_ответ>')
ANSWER_END_PATTERN = re.compile('|'.join(map(re.escape, ANSWER_END_ARTIFACTS)), re.IGNORECASE)
EXTRA_MARKER_PATTERN = re.compile(r'</extra\?>?', re.IGNORECASE)
STREAM_MARKERS = (*ANSWER_END_ARTIFACTS, '</extra?', '</extra?>')


def remove_extra_duplicates(text, partial=False):
    parts = EXTRA_MARKER_PATTERN.split(text)
    if partial and len(parts) > 1:
        # Keep the extra segment buffered until we can distinguish a repeated
        # answer from genuinely new content.
        return parts[0]
    kept = [parts[0]]
    for part in parts[1:]:
        previous = re.sub(r'\s|\ufe0f', '', kept[-1])
        candidate = re.sub(r'\s|\ufe0f', '', part)
        if not candidate:
            continue
        duplicate = candidate == previous or (
            min(len(previous), len(candidate)) >= 40
            and SequenceMatcher(None, previous, candidate, autojunk=False).ratio() >= 0.97
        )
        if not duplicate:
            kept.append(part)
    return ''.join(kept)


def filter_answer_artifacts(text, partial=False):
    """Remove observed model markers while preserving the surrounding text."""
    text = ANSWER_END_PATTERN.sub('', text)
    if partial:
        # A tag can span SSE chunks. Hold back its unfinished prefix so it
        # cannot briefly appear in a Telegram draft.
        for size in range(min(len(text), max(map(len, STREAM_MARKERS)) - 1), 0, -1):
            if any(marker.startswith(text[-size:].casefold()) for marker in STREAM_MARKERS):
                text = text[:-size]
                break
    return remove_extra_duplicates(text, partial)


def clean_answer_history(history):
    result = []
    for message in history or []:
        if message.get('role') == 'assistant':
            content = filter_answer_artifacts(message['content'])
            if not content.strip():
                continue
            message = dict(message, content=content)
        result.append(message)
    return result


def response_text(result):
    try:
        content = result['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError('Provider response has no message') from error
    if not isinstance(content, str) or not content.strip():
        raise ValueError('Provider returned an empty answer')
    return content


async def stream_answer(query, session, history=None, system_prompt=None):
    payload = {
        'model': config.AI_MODEL,
        'messages': [
            {'role': 'system', 'content': get_style().system_prompt if system_prompt is None else system_prompt},
            *clean_answer_history(history),
            {'role': 'user', 'content': query},
        ],
        'max_tokens': config.AI_MAX_TOKENS,
        'stream': True,
    }
    if config.AI_REASONING_EFFORT:
        payload['reasoning_effort'] = config.AI_REASONING_EFFORT
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


async def request_answer(query, session, history=None, update_callback=None, system_prompt=None):
    return await retry_once(lambda: _request_answer(query, session, history, update_callback, system_prompt))


async def _request_answer(query, session, history=None, update_callback=None, system_prompt=None):
    parts = []
    last_length = 0
    last_update = 0
    async with aclosing(stream_answer(query, session, history, system_prompt)) as stream:
        async for chunk in stream:
            parts.append(chunk)
            partial = filter_answer_artifacts(''.join(parts), partial=True)
            now = time.monotonic()
            if update_callback and len(partial) - last_length >= 80 and now - last_update >= 0.8:
                await update_callback(partial)
                last_update, last_length = now, len(partial)
    answer = filter_answer_artifacts(''.join(parts)).strip()
    if not answer:
        raise ValueError('Provider returned an empty answer')
    return answer
