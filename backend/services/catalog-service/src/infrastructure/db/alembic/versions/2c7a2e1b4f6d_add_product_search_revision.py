"""add persistent Product search revision

Revision ID: 2c7a2e1b4f6d
Revises: f2b4a6c8d0e1
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2c7a2e1b4f6d"
down_revision: Union[str, Sequence[str], None] = "f2b4a6c8d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "search_revision",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )


def downgrade() -> None:
    op.drop_column("products", "search_revision")
