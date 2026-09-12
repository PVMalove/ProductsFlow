"""Единый реестр ожидаемых Result-ошибок payment domain/application (ADR 0014,
issue #368). Используется только domain и application — infrastructure сюда
не обращается."""

from kernel_domain.errors import Error


class PaymentErrors:
    @staticmethod
    def invalid_amount() -> Error:
        return Error.validation(
            "invalid_amount",
            "Сумма авторизации должна быть положительной",
            invalid_field="amount",
        )

    @staticmethod
    def unknown_test_scenario_token() -> Error:
        """`payment_method_token` не входит в распознанный сценарный словарь
        Test PSP (архитектурный бриф D4) — не тихий дефолт на `success`."""
        return Error.validation(
            "unknown_test_scenario_token",
            "Неизвестный сценарный токен Test PSP",
            invalid_field="payment_method_token",
        )

    @staticmethod
    def authorization_not_found() -> Error:
        return Error.not_found(
            "authorization_not_found",
            "Авторизация платежа не найдена",
        )

    @staticmethod
    def idempotency_conflict() -> Error:
        """То же значение `Idempotency-Key`, другое тело запроса (ADR 0016:31).
        Общая ошибка для всех трёх write-операций (authorize/void/capture)."""
        return Error.conflict(
            "idempotency_conflict",
            "Idempotency-Key уже использован с другим телом запроса",
        )

    @staticmethod
    def invalid_authorization_state() -> Error:
        """Операция (void/capture) недопустима для текущего статуса
        авторизации — не отдельный ключ по сути, тот же класс, что
        `capture_pending_reconciliation`, но без обязательной сверки."""
        return Error.conflict(
            "invalid_authorization_state",
            "Операция недопустима для текущего статуса авторизации",
        )

    @staticmethod
    def capture_pending_reconciliation() -> Error:
        """ADR 0016: «повторять capture до сверки результата у payment-service
        по идемпотентному ключу запрещено» — неизвестный исход предыдущего
        capture блокирует новый ключ отдельным, узнаваемым кодом."""
        return Error.conflict(
            "capture_pending_reconciliation",
            "Результат предыдущего capture не подтверждён — требуется сверка",
        )
