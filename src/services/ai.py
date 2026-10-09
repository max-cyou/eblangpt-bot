import config
import prompt

HEADERS = {
    'Authorization': f'Bearer {config.AI_API_KEY}'
}

async def request_answer(query, session, history=None):
    payload = {
        'model': config.AI_MODEL,
        'messages': [
            {'role': 'system', 'content': prompt.SYSTEM_PROMPT},
            *(history or []),
            {'role': 'user', 'content': query},
        ],
        'max_tokens': 200,
        'stream': False,
    }

    async with session.post(config.AI_API_URL, headers=HEADERS, json=payload) as response:
        response.raise_for_status()
        result = await response.json()
        return result['choices'][0]['message']['content']
