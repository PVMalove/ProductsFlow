"""Перечисление зарегистрированных `command_type` -> message-driven handler
в `api/reservation_commands.py` (issue #370, Seams for TDD #6, по духу
`test_cqrs_inventory_seams.py`, но для message-driven регистра — отдельный
файл, не правка существующего: area его assertion — только FastAPI-exposed
handlers, D8) — ловит забытую регистрацию `inventory.reserve.v1`/
`inventory.release.v1` в `api/worker.py::main()`."""

from api.reservation_commands import (
    COMMAND_HANDLERS,
    handle_release_command,
    handle_reserve_command,
)


def test_reservation_command_handlers_cover_reserve_and_release() -> None:
    assert COMMAND_HANDLERS == {
        "inventory.reserve.v1": handle_reserve_command,
        "inventory.release.v1": handle_release_command,
    }
