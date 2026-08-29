import httpx


class CountingTransport(httpx.AsyncBaseTransport):
    """Оборачивает транспорт и считает фактические HTTP-запросы — тесты
    проверяют троттлинг refetch по числу обращений, а не по side effect."""

    def __init__(self, wrapped: httpx.AsyncBaseTransport) -> None:
        self._wrapped = wrapped
        self.request_count = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.request_count += 1
        return await self._wrapped.handle_async_request(request)


class FlakyOnceTransport(httpx.AsyncBaseTransport):
    """Первые `fail_times` запросов падают с сетевой ошибкой, дальше — как
    обычно. Имитирует identity, ещё не поднявшийся к моменту preload."""

    def __init__(self, wrapped: httpx.AsyncBaseTransport, fail_times: int = 1) -> None:
        self._wrapped = wrapped
        self._remaining_failures = fail_times

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise httpx.ConnectError("identity ещё не поднялся", request=request)
        return await self._wrapped.handle_async_request(request)
