from kernel_platform.unit_of_work import SqlAlchemyUnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession

from domain.repositories import TicketRepository
from domain.unit_of_work import SupportUnitOfWork
from infrastructure.db.ticket_repository import SqlTicketRepository


class SqlSupportUnitOfWork(SqlAlchemyUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.tickets: TicketRepository = SqlTicketRepository(session)


# Статическая структурная проверка: mypy убеждается, что конкретная
# реализация удовлетворяет каждую операцию, требуемую доменным контрактом
# UnitOfWork.
_support_unit_of_work_implementation: type[SupportUnitOfWork] = SqlSupportUnitOfWork
