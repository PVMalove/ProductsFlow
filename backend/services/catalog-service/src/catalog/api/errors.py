from fastapi import HTTPException, status
from kernel_domain.errors import Error, ErrorType

_STATUS_BY_TYPE: dict[ErrorType, int] = {
    ErrorType.VALIDATION: status.HTTP_400_BAD_REQUEST,
    ErrorType.NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorType.CONFLICT: status.HTTP_409_CONFLICT,
    ErrorType.FORBIDDEN: status.HTTP_403_FORBIDDEN,
    ErrorType.UNAUTHORIZED: status.HTTP_401_UNAUTHORIZED,
    ErrorType.PROBLEM: status.HTTP_400_BAD_REQUEST,
    ErrorType.FAILURE: status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def to_http_exception(error: Error) -> HTTPException:
    return HTTPException(
        status_code=_STATUS_BY_TYPE[error.type], detail=error.description
    )
