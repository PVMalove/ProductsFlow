"""Базовый класс ожидаемых application-исключений payment-service (ADR 0003).

Сегодня payment-service не поднимает ни одного собственного подкласса — все
ожидаемые сбои (невалидная сумма, отсутствующая авторизация, конфликт
idempotency-ключа) выражены через `Result`/`ApiError`
(`kernel_platform.http.match`), а недоступность identity — через
`HTTPException` в security-зависимости (fail-closed). База остаётся
расширяемой точкой для `register_error_handlers`, тем же способом, что
identity/catalog/support/inventory уже её объявляют."""


class ApplicationError(Exception):
    code: str
    message: str
    status_code: int

    def __init__(self) -> None:
        super().__init__(self.message)
