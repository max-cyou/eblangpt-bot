from services.errors import REQUEST_ERRORS


async def retry_once(operation):
    for attempt in range(2):
        try:
            return await operation()
        except REQUEST_ERRORS:
            if attempt == 1:
                raise
