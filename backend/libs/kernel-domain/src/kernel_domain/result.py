from kernel_domain.errors import Error


class Result[T]:
    """Явный успех/неудача без исключений на ожидаемых сбоях бизнес-логики
    (ADR 0013). `Result` без параметра — то же самое с T как Any; отдельного
    беззначенческого класса не заводим, `Result.ok(None)` покрывает void-кейс."""

    def __init__(self, *, value: T | None, error: Error | None, is_ok: bool) -> None:
        self._value = value
        self._error = error
        self._is_ok = is_ok

    @classmethod
    def ok(cls, value: T) -> "Result[T]":
        return cls(value=value, error=None, is_ok=True)

    @classmethod
    def fail(cls, error: Error) -> "Result[T]":
        return cls(value=None, error=error, is_ok=False)

    @property
    def is_ok(self) -> bool:
        return self._is_ok

    @property
    def is_err(self) -> bool:
        return not self._is_ok

    @property
    def value(self) -> T:
        if not self._is_ok:
            raise ValueError("Result в состоянии ошибки не несёт значения")
        return self._value  # type: ignore[return-value]

    @property
    def error(self) -> Error:
        if self._is_ok:
            raise ValueError("Успешный Result не несёт ошибки")
        assert self._error is not None
        return self._error
