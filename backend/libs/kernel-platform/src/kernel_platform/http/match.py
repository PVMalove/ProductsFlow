"""Generic domain-`Result`-в-HTTP unwrapping (ADR 0031)."""

from kernel_domain.result import Result

from kernel_platform.http.envelope import ApiResponse
from kernel_platform.http.errors import ApiError, status_code_for_error_type


def match_result[T](result: Result[T]) -> ApiResponse[T]:
    """Успешный `Result` заворачивается в `ApiResponse`; неуспешный поднимает
    `ApiError`, перехватываемый `register_error_handlers` и превращаемый в
    структурированный `ErrorResponse` с сохранением `Error.code`."""
    if result.is_err:
        error = result.error
        raise ApiError(
            status_code=status_code_for_error_type(error.type),
            code=error.code,
            message=error.description,
        )
    return ApiResponse(data=result.value)


def match_created[T](result: Result[T]) -> ApiResponse[T]:
    """Семантический алиас `match_result` для create-эндпоинтов — HTTP 201
    по-прежнему задаёт только декоратор роута, не эта функция."""
    return match_result(result)
