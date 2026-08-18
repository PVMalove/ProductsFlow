from base64 import urlsafe_b64encode
from datetime import datetime

import pytest

from app.pagination import Cursor, InvalidCursorError, decode_cursor, encode_cursor


def test_decode_cursor_recovers_the_position_it_was_encoded_from():
    created_at = datetime(2026, 8, 18, 12, 30, 45, 123456)

    token = encode_cursor(created_at, 42)

    assert decode_cursor(token) == Cursor(created_at=created_at, id=42)


def test_encode_cursor_produces_an_opaque_token_not_containing_the_raw_id():
    token = encode_cursor(datetime(2026, 8, 18, 12, 30, 45), 42)

    assert "42" not in token


def test_decode_cursor_rejects_a_token_that_is_not_valid_base64():
    with pytest.raises(InvalidCursorError):
        decode_cursor("not-valid-base64!!!")


def test_decode_cursor_rejects_a_token_missing_the_id_part():
    malformed = urlsafe_b64encode(b"2026-08-18T12:30:45").decode("ascii")

    with pytest.raises(InvalidCursorError):
        decode_cursor(malformed)


def test_decode_cursor_rejects_a_token_with_a_non_integer_id():
    malformed = urlsafe_b64encode(b"2026-08-18T12:30:45|not-an-id").decode("ascii")

    with pytest.raises(InvalidCursorError):
        decode_cursor(malformed)


def test_decode_cursor_rejects_a_token_with_an_unparseable_timestamp():
    malformed = urlsafe_b64encode(b"not-a-date|42").decode("ascii")

    with pytest.raises(InvalidCursorError):
        decode_cursor(malformed)
