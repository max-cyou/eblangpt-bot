from dataclasses import dataclass, field
from typing import Mapping

from prompts.default import SYSTEM_PROMPT as DEFAULT_PROMPT
from prompts.schizo import SYSTEM_PROMPT as SCHIZO_PROMPT
from fallbacks.default import FALLBACKS as DEFAULT_FALLBACKS
from fallbacks.schizo import FALLBACKS as SCHIZO_FALLBACKS


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
}


def get_style(style_id=None):
    return STYLES.get(style_id, STYLES[DEFAULT_STYLE_ID])
