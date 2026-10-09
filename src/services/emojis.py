import random
import re

CASUAL_RESPONSE_LIMIT = 160
COMMON_EMOJIS = ('😈', '✅', '👍', '💪')
RARE_EMOJIS = ('🔥', '🥶', '😂', '🤝')
EMOJI_POOL = COMMON_EMOJIS + RARE_EMOJIS
COMMON_EMOJI_WEIGHTS = {'😈': 4, '✅': 1, '👍': 3, '💪': 3}
EMOJI_PATTERN = re.compile('|'.join(map(re.escape, sorted(EMOJI_POOL, key=len, reverse=True))))
ANY_EMOJI_PATTERN = re.compile(
    r'(?:[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u27BF](?:\ufe0f)?)'
    r'(?:\u200d[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u27BF](?:\ufe0f)?)*'
)
emoji_random = random.SystemRandom()


def add_emojis_to_casual_answer(text, history):
    protected_markers = (chr(96) * 3, chr(96), '$', '|', '[', ']', '<', '>', '**', '__')
    has_rich_blocks = re.search(r'(?m)^(?:#{1,6}|[-+*]|\d+\.)\s', text)

    if (
        len(text) > CASUAL_RESPONSE_LIMIT
        or any(marker in text for marker in protected_markers)
        or has_rich_blocks
    ):
        return text

    text = ANY_EMOJI_PATTERN.sub(
        lambda match: match.group().replace('\ufe0f', '')
        if match.group().replace('\ufe0f', '') in EMOJI_POOL
        else '',
        text,
    )
    target_count = emoji_random.choice((1, 1, 1, 2))
    emoji_number = 0

    def keep_limited_emojis(match):
        nonlocal emoji_number
        emoji_number += 1
        return match.group() if emoji_number <= target_count else ''

    text = EMOJI_PATTERN.sub(keep_limited_emojis, text)
    text = re.sub(rf'\s+(?={EMOJI_PATTERN.pattern})', '', text)
    parts = re.split(r'(\s+)', text)
    word_indexes = [index for index, part in enumerate(parts) if part and not part.isspace()]

    if len(word_indexes) < 2:
        return text

    inner_indexes = word_indexes[:-1]
    last_word_index = word_indexes[-1]
    existing_emojis = EMOJI_PATTERN.findall(''.join(parts))

    if existing_emojis and not any(EMOJI_PATTERN.search(parts[index]) for index in inner_indexes):
        match = EMOJI_PATTERN.search(parts[last_word_index])
        if match:
            emoji = match.group()
            parts[last_word_index] = (
                parts[last_word_index][:match.start()] + parts[last_word_index][match.end():]
            )
            parts[emoji_random.choice(inner_indexes)] += emoji

    used_emojis = set(EMOJI_PATTERN.findall(''.join(parts)))
    existing_count = len(EMOJI_PATTERN.findall(''.join(parts)))
    previous_emojis = {
        emoji
        for item in history[-4:]
        if item.get('role') == 'assistant'
        for emoji in EMOJI_PATTERN.findall(item.get('content', ''))
    }
    candidates = []
    available = [emoji for emoji in EMOJI_POOL if emoji not in used_emojis]
    while available and len(candidates) < target_count - existing_count:
        fresh = [emoji for emoji in available if emoji not in previous_emojis]
        choices = fresh or available
        common = [emoji for emoji in choices if emoji in COMMON_EMOJIS]
        rare = [emoji for emoji in choices if emoji in RARE_EMOJIS]
        group = common if common and (not rare or emoji_random.random() < 0.85) else rare
        emoji = (
            emoji_random.choices(
                group,
                weights=[COMMON_EMOJI_WEIGHTS[item] for item in group],
                k=1,
            )[0]
            if group is common
            else emoji_random.choice(group)
        )
        candidates.append(emoji)
        available.remove(emoji)

    positions = inner_indexes.copy()
    emoji_random.shuffle(positions)
    for offset, emoji in enumerate(candidates[:max(0, target_count - existing_count)]):
        parts[positions[offset % len(positions)]] += emoji

    return ''.join(parts)
