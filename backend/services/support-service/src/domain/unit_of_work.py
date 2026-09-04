from typing import Protocol

from kernel_platform.unit_of_work import UnitOfWork

from domain.repositories import TicketRepository


class SupportUnitOfWork(UnitOfWork, Protocol):
    tickets: TicketRepository
