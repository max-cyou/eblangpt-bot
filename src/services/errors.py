import asyncio

import aiohttp
from telebot.asyncio_helper import ApiException


# Catch expected external failures; programming errors still reach the logger.
REQUEST_ERRORS = (aiohttp.ClientError, asyncio.TimeoutError, ValueError, RuntimeError, ApiException)


def fallback_text(error, kind='ai'):
    if isinstance(error, asyncio.TimeoutError):
        return 'слыш😈 модель задумалась💪 попробуй чуть позже'
    if isinstance(error, aiohttp.ClientResponseError):
        if error.status == 429:
            return 'вась😈 очередь забита💪 дай минутку и попробуй снова'
        if error.status in (401, 403):
            return 'э😈 доступ к модели отвалился💪 уже надо чинить'
        return 'э😈 сервер отвалился💪 попробуй позже'
    if isinstance(error, aiohttp.ClientConnectionError):
        return 'вась😈 до сервера не достучался💪 попробуй позже'
    if kind == 'image':
        return 'не разглядел пикчу😈 попробуй другую или отправь позже'
    if kind == 'audio':
        return 'не разобрал войс😈 попробуй еще раз'
    if kind == 'document':
        return 'не прочитал файл😈 отправь текстовый файл поменьше'
    return 'э😈 ответ потерялся💪 попробуй еще раз'


def failure_details(error):
    """Avoid logging provider URLs, payloads or credentials embedded in errors."""
    status = getattr(error, 'status', None) or getattr(error, 'error_code', None)
    return f'{type(error).__name__}, status={status}'
