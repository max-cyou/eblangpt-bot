import asyncio

import aiohttp
from telebot.asyncio_helper import ApiException
from fallbacks.common import FALLBACKS as COMMON_FALLBACKS
from styles import get_style


# Catch expected external failures; programming errors still reach the logger.
REQUEST_ERRORS = (aiohttp.ClientError, asyncio.TimeoutError, ValueError, RuntimeError, ApiException)


def fallback_key(error, kind):
    specific = {
        'image_too_large', 'audio_too_large', 'document_too_large',
        'document_not_text', 'vision_not_configured', 'audio_not_configured',
    }
    if isinstance(error, (ValueError, RuntimeError)) and str(error) in specific:
        return str(error)
    if isinstance(error, asyncio.TimeoutError):
        return 'timeout'
    if isinstance(error, aiohttp.ClientResponseError):
        if error.status == 429:
            return 'rate_limit'
        if error.status in (401, 403):
            return 'access'
        return 'server'
    if isinstance(error, aiohttp.ClientConnectionError):
        return 'connection'
    return kind if kind in ('image', 'audio', 'document') else 'ai'


def fallback_text(error, kind='ai', style=None):
    style = style or get_style()
    key = fallback_key(error, kind)
    return style.fallbacks.get(key, COMMON_FALLBACKS[key])


def failure_details(error):
    """Avoid logging provider URLs, payloads or credentials embedded in errors."""
    status = getattr(error, 'status', None) or getattr(error, 'error_code', None)
    details = f'{type(error).__name__}, status={status}'
    safe_reasons = {
        'Provider response has no message': 'missing_message',
        'Provider returned an empty answer': 'empty_answer',
        'Invalid provider stream': 'invalid_stream',
        'Provider reported a stream error': 'stream_error',
        'Invalid provider stream event': 'invalid_stream_event',
        'Invalid stream content': 'invalid_stream_content',
        'Invalid vision response': 'invalid_vision_response',
        'Vision description is empty': 'empty_vision_description',
        'Empty audio transcription': 'empty_audio_transcription',
    }
    if isinstance(error, ValueError) and str(error) in safe_reasons:
        details += f', reason={safe_reasons[str(error)]}'
    return details
