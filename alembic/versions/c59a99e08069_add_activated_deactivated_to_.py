"""add activated deactivated to productauditaction

Revision ID: c59a99e08069
Revises: 8de74246791b
Create Date: 2026-08-19 17:09:41.813705

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c59a99e08069'
down_revision: Union[str, Sequence[str], None] = '8de74246791b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE productauditaction ADD VALUE 'ACTIVATED'")
    op.execute("ALTER TYPE productauditaction ADD VALUE 'DEACTIVATED'")


def downgrade() -> None:
    """Downgrade schema."""
    # Postgres не поддерживает удаление значений ENUM (нет DROP VALUE) без
    # пересоздания типа и всех таблиц, которые его используют.
    raise NotImplementedError(
        "Откат недоступен: Postgres не поддерживает удаление значений ENUM"
    )
