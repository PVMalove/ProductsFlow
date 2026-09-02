import uuid
from dataclasses import dataclass

from application.ports import UserDeletionPort


@dataclass(frozen=True)
class ProcessUserDeletionCommand:
    message_id: int
    user_id: uuid.UUID


class ProcessUserDeletionCommandHandler:
    """Apply a user deletion through the transactional support port."""

    def __init__(self, repository: UserDeletionPort) -> None:
        self._repository = repository

    async def execute(self, command: ProcessUserDeletionCommand) -> bool:
        return await self._repository.process_user_deleted(
            message_id=command.message_id,
            user_id=command.user_id,
        )
