from typing import NoReturn, TypeVar

from fastapi import HTTPException, status
from kernel_domain.result import Result

_ResultValue = TypeVar("_ResultValue")


def raise_command_error(result: Result[_ResultValue]) -> NoReturn:
    error = result.error
    status_code = {
        "CONFLICT": status.HTTP_409_CONFLICT,
        "VALIDATION": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "UNAUTHORIZED": status.HTTP_401_UNAUTHORIZED,
        "FORBIDDEN": status.HTTP_403_FORBIDDEN,
        "NOT_FOUND": status.HTTP_404_NOT_FOUND,
    }.get(error.type.value, status.HTTP_500_INTERNAL_SERVER_ERROR)
    headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None
    raise HTTPException(
        status_code=status_code,
        detail=error.description,
        headers=headers,
    )
