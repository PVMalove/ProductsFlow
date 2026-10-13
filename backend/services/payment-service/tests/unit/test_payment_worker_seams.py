"""Перечисление зарегистрированных `command_type` -> message-driven handler в
`api/payment_commands.py` (issue #371, Seams for TDD #2, по духу inventory's
`test_reservation_worker_seams.py`) — ловит забытую регистрацию
`payment.authorize.v1`/`payment.void.v1` в `api/worker.py::main()`."""

from api.workers.commands.payment_commands import (
    COMMAND_HANDLERS,
    handle_authorize_command,
    handle_capture_command,
    handle_lookup_capture_command,
    handle_void_command,
)


def test_payment_command_handlers_cover_authorize_void_capture_and_lookup() -> None:
    assert COMMAND_HANDLERS == {
        "payment.authorize.v1": handle_authorize_command,
        "payment.void.v1": handle_void_command,
        "payment.capture.v1": handle_capture_command,
        "payment.lookup_capture.v1": handle_lookup_capture_command,
    }
