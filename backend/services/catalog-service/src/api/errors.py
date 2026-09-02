from fastapi import HTTPException
from kernel_domain.errors import Error
from kernel_platform.http.errors import status_code_for_error_type


def to_http_exception(error: Error) -> HTTPException:
    return HTTPException(
        status_code=status_code_for_error_type(error.type), detail=error.description
    )
