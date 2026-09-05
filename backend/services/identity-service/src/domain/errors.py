"""Единый реестр ожидаемых Result-ошибок identity domain/application (ADR 0014).

Устраняет сырые конструкторы `Error(...)` в пользу стабильных `snake_case`
кодов, безопасных описаний и публичных `invalid_field`. Используется только
domain и application — infrastructure сюда не обращается."""

from kernel_domain.errors import Error


class IdentityErrors:
    @staticmethod
    def invalid_email() -> Error:
        return Error.validation(
            "invalid_email",
            "Некорректный формат email",
            invalid_field="email",
        )

    @staticmethod
    def password_too_short() -> Error:
        return Error.validation(
            "password_too_short",
            "Пароль должен содержать минимум 8 символов",
            invalid_field="password",
        )

    @staticmethod
    def password_missing_lowercase() -> Error:
        return Error.validation(
            "password_missing_lowercase",
            "Пароль должен содержать строчную букву",
            invalid_field="password",
        )

    @staticmethod
    def password_missing_digit() -> Error:
        return Error.validation(
            "password_missing_digit",
            "Пароль должен содержать цифру",
            invalid_field="password",
        )

    @staticmethod
    def email_already_registered() -> Error:
        return Error.conflict("email_already_registered", "Email уже зарегистрирован")

    @staticmethod
    def invalid_credentials() -> Error:
        return Error.unauthorized("invalid_credentials", "Неверный email или пароль")

    @staticmethod
    def old_password_mismatch() -> Error:
        # Код намеренно совпадает с invalid_credentials() — это тот же публичный
        # код, что и раньше отдавал сырой конструктор change-password, только с
        # контекстным описанием.
        return Error.unauthorized("invalid_credentials", "Текущий пароль не совпадает")

    @staticmethod
    def user_deactivated() -> Error:
        return Error.forbidden("user_deactivated", "Пользователь деактивирован")

    @staticmethod
    def already_deactivated() -> Error:
        return Error.conflict("already_deactivated", "Пользователь уже деактивирован")

    @staticmethod
    def user_deleted() -> Error:
        return Error.forbidden(
            "user_deleted", "Удалённая учётная запись не может быть активирована"
        )

    @staticmethod
    def already_active() -> Error:
        return Error.conflict("already_active", "Пользователь уже активен")

    @staticmethod
    def already_deleted() -> Error:
        return Error.conflict("already_deleted", "Учётная запись уже удалена")

    @staticmethod
    def role_unchanged() -> Error:
        return Error.conflict("role_unchanged", "Пользователь уже имеет эту роль")

    @staticmethod
    def cannot_deactivate_self() -> Error:
        return Error.forbidden(
            "cannot_deactivate_self",
            "Пользователь не может деактивировать самого себя",
        )

    @staticmethod
    def user_not_found() -> Error:
        return Error.not_found("user_not_found", "Пользователь не найден")
