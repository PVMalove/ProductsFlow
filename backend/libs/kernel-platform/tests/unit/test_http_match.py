"""ADR 0031: generic success envelope + `Result`-to-HTTP unwrapping."""

import pytest
from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result

from kernel_platform.http.envelope import ApiResponse
from kernel_platform.http.errors import ApiError
from kernel_platform.http.match import match_created, match_result


def test_api_response_defaults_meta_to_an_empty_object() -> None:
    response = ApiResponse[int](data=1)

    assert response.data == 1
    assert response.meta == {}


def test_match_result_wraps_an_ok_result_in_the_envelope() -> None:
    result: Result[int] = Result.ok(42)

    response = match_result(result)

    assert response == ApiResponse[int](data=42, meta={})


def test_match_result_raises_api_error_with_the_mapped_status_and_domain_code() -> None:
    error = Error(
        code="invalid_name", description="Плохое имя", type=ErrorType.VALIDATION
    )
    result: Result[int] = Result.fail(error)

    with pytest.raises(ApiError) as exc_info:
        match_result(result)

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "invalid_name"
    assert exc_info.value.message == "Плохое имя"


def test_match_created_behaves_exactly_like_match_result() -> None:
    ok: Result[str] = Result.ok("created")
    assert match_created(ok) == match_result(Result.ok("created"))

    error = Error(
        code="already_active", description="Конфликт", type=ErrorType.CONFLICT
    )
    with pytest.raises(ApiError) as exc_info:
        match_created(Result.fail(error))
    assert exc_info.value.status_code == 409
