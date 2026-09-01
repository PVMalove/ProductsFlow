from fastapi import HTTPException, status
from kernel_domain.errors import Error, ErrorType

from application.errors import (
    IdentityUnavailableError,
    ProductAccessDeniedError,
    ProductImageNotFoundError,
    ProductNotFoundError,
)

_STATUS_BY_TYPE: dict[ErrorType, int] = {
    ErrorType.VALIDATION: status.HTTP_400_BAD_REQUEST,
    ErrorType.NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorType.CONFLICT: status.HTTP_409_CONFLICT,
    ErrorType.FORBIDDEN: status.HTTP_403_FORBIDDEN,
    ErrorType.UNAUTHORIZED: status.HTTP_401_UNAUTHORIZED,
    ErrorType.PROBLEM: status.HTTP_400_BAD_REQUEST,
    ErrorType.FAILURE: status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def to_http_exception(error: Error | Exception) -> HTTPException:
    if isinstance(error, ProductNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден"
        )
    if isinstance(error, ProductAccessDeniedError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Нет прав на этот товар"
        )
    if isinstance(error, ProductImageNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="У товара нет картинки!"
        )
    if isinstance(error, IdentityUnavailableError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="identity-service недоступен",
        )
    assert isinstance(error, Error)
    return HTTPException(
        status_code=_STATUS_BY_TYPE[error.type], detail=error.description
    )
