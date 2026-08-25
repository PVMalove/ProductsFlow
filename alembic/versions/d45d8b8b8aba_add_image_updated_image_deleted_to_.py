"""add image_updated image_deleted to productauditaction

Revision ID: d45d8b8b8aba
Revises: f1dc65449b9c
Create Date: 2026-08-25 17:27:32.939918

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd45d8b8b8aba'
down_revision: Union[str, Sequence[str], None] = 'f1dc65449b9c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE productauditaction ADD VALUE 'IMAGE_UPDATED'")
    op.execute("ALTER TYPE productauditaction ADD VALUE 'IMAGE_DELETED'")


def downgrade() -> None:
    """Downgrade schema."""
    # Postgres не поддерживает удаление значений ENUM (нет DROP VALUE) без
    # пересоздания типа и всех таблиц, которые его используют.
    raise NotImplementedError(
        "Откат недоступен: Postgres не поддерживает удаление значений ENUM"
    )
