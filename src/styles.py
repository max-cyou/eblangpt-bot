from dataclasses import dataclass, field
from typing import Mapping

from prompts.default import SYSTEM_PROMPT as DEFAULT_PROMPT
from prompts.schizo import SYSTEM_PROMPT as SCHIZO_PROMPT
from fallbacks.default import FALLBACKS as DEFAULT_FALLBACKS
from fallbacks.schizo import FALLBACKS as SCHIZO_FALLBACKS
from prompts.zoomer import SYSTEM_PROMPT as ZOOMER_PROMPT
from fallbacks.zoomer import FALLBACKS as ZOOMER_FALLBACKS
from prompts.emoji import SYSTEM_PROMPT as EMOJI_PROMPT
from fallbacks.emoji import FALLBACKS as EMOJI_FALLBACKS


@dataclass(frozen=True)
class Style:
    id: str
    name: str
    description: str
    system_prompt: str
    auto_emojis: bool = False
    fallbacks: Mapping[str, str] = field(default_factory=dict)
    statuses: Mapping[str, str] = field(default_factory=dict)


DEFAULT_STYLE_ID = 'default'

STYLES = {
    'default': Style(
        id='default', name='eblangpt 2.0', description='почти классический eblangpt',
        system_prompt=DEFAULT_PROMPT, auto_emojis=True,
        statuses={
            'ai': '😈 бжжж ответ calculating💪',
            'image': 'смотрю пикчу😈 погоди вась',
            'audio': 'слушаю войс😈 погоди вась',
        },
        fallbacks=DEFAULT_FALLBACKS,
    ),
    'schizo': Style(
        id='schizo', name='шизоeblan', description='конченный шиз',
        system_prompt=SCHIZO_PROMPT,
        fallbacks=SCHIZO_FALLBACKS,
        statuses={
            'ai': 'бляя... ААА мыслы в ggучу собырею @monk pashol naxxuy 🤝 ААА',
            'image': 'бляя... пыggчу рессметрывею глеземы @vatnouser ищек бля 🥀 пыggчу',
            'audio': 'бляя... войс в ушах ggручу @monk pashol naxxuy 🤝 войс',
        },
    ),
    'zoomer': Style(
        id='zoomer', name='зумер', description='злой зумер, матерится через слово, но по делу',
        system_prompt=ZOOMER_PROMPT,
        fallbacks=ZOOMER_FALLBACKS,
        statuses={
            'ai': 'ща нахуй, вась, думаю 🗿',
            'image': 'смотрю пикчу, не торопи бля 💀',
            'audio': 'слушаю твой войс, вась, пиздец 😮‍💨',
        },
    ),
    'emoji': Style(
        id='emoji', name='эмодзи-еблан', description='тот же еблан но вместо слов только эмодзи',
        system_prompt=EMOJI_PROMPT,
        fallbacks=EMOJI_FALLBACKS,
        statuses={
            'ai': '🧠⚙️😈',
            'image': '🖼️👀😈',
            'audio': '🎧👂😈',
        },
    ),
}


def get_style(style_id=None):
    return STYLES.get(style_id, STYLES[DEFAULT_STYLE_ID])
