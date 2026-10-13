"""Базовый класс ожидаемых application-исключений inventory-service (ADR 0003).

Сегодня inventory-service не поднимает ни одного собственного подкласса —
все ожидаемые сбои (негативный остаток, отсутствующая запись) выражены через
`Result`/`ApiError` (`kernel_platform.http.match`), а недоступность identity —
через `HTTPException` в security-зависимости (fail-closed, issue #367). База
остаётся расширяемой точкой для `register_error_handlers`, тем же способом,
что identity/catalog/support уже её объявляют."""


class ApplicationError(Exception):
    code: str
    message: str
    status_code: int

    def __init__(self) -> None:
        super().__init__(self.message)
