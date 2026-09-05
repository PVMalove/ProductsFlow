"""Единый реестр ожидаемых Result-ошибок support domain/application (ADR 0014).

Устраняет сырые конструкторы `Error(...)` в пользу стабильных кодов,
безопасных описаний и публичных `invalid_field`. Используется только domain
и application — infrastructure сюда не обращается.

Схема двухуровневая, отражая существующий трансляционный шов
(`TicketRepository._raise_for_error`, issue #253): внутренние snake_case-коды
ниже — то, что реально возвращают `Ticket`/`TicketMessage` в `Result.fail`;
они немедленно поглощаются репозиторием и наружу не выходят. Внешние коды —
то, что видит BFF после трансляции; часть из них исторически ЗАГЛАВНЫЕ и
сохраняются как есть, чтобы не менять уже опубликованный контракт ошибок."""

from kernel_domain.errors import Error


class SupportErrors:
    @staticmethod
    def invalid_subject() -> Error:
        return Error.validation(
            "invalid_subject",
            "Тема обращения должна содержать от 1 до 200 символов",
            invalid_field="subject",
        )

    @staticmethod
    def invalid_first_message() -> Error:
        return Error.validation(
            "invalid_first_message",
            "Сообщение должно содержать от 1 до 10000 символов",
            invalid_field="first_message",
        )

    @staticmethod
    def invalid_body() -> Error:
        return Error.validation(
            "invalid_body",
            "Сообщение должно содержать от 1 до 10000 символов",
            invalid_field="body",
        )

    @staticmethod
    def ticket_closed() -> Error:
        return Error.conflict("ticket_closed", "Тикет закрыт")

    @staticmethod
    def invalid_status_transition() -> Error:
        return Error.conflict(
            "invalid_status_transition", "Недопустимый переход статуса тикета"
        )

    @staticmethod
    def message_not_found() -> Error:
        return Error.not_found("message_not_found", "Сообщение не найдено")

    @staticmethod
    def message_immutable() -> Error:
        return Error.conflict("message_immutable", "Сообщение нельзя изменить")

    @staticmethod
    def message_already_deleted() -> Error:
        return Error.conflict("message_already_deleted", "Сообщение уже удалено")

    @staticmethod
    def ticket_not_found() -> Error:
        return Error.not_found("TICKET_NOT_FOUND", "Тикет не найден")

    @staticmethod
    def ticket_message_not_found() -> Error:
        return Error.not_found("TICKET_MESSAGE_NOT_FOUND", "Тикет не найден")

    @staticmethod
    def ticket_message_immutable(action: str) -> Error:
        return Error.conflict("TICKET_MESSAGE_IMMUTABLE", f"Сообщение нельзя {action}")

    @staticmethod
    def ticket_closed_conflict() -> Error:
        return Error.conflict("TICKET_CLOSED", "Закрытый тикет нельзя изменять")

    @staticmethod
    def ticket_status_transition_rejected() -> Error:
        return Error.conflict(
            "INVALID_STATUS_TRANSITION", "Недопустимый переход статуса тикета"
        )

    @staticmethod
    def forbidden() -> Error:
        return Error.forbidden("FORBIDDEN", "Доступ только для администраторов!")
