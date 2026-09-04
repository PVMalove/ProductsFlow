import uuid
from dataclasses import dataclass

from domain.unit_of_work import SupportUnitOfWork


@dataclass(frozen=True)
class ProcessUserDeletionCommand:
    message_id: int
    user_id: uuid.UUID


class ProcessUserDeletionCommandHandler:
    """Apply a user deletion through the transactional support port."""

    def __init__(self, uow: SupportUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: ProcessUserDeletionCommand) -> bool:
        async with self._uow:
            processed = await self._uow.tickets.process_user_deleted(
                message_id=command.message_id,
                user_id=command.user_id,
            )
            if processed:
                await self._uow.commit()
        return processed
