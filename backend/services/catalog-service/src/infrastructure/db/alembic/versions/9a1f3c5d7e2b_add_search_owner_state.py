"""add search owner state for catalog-search-worker

Revision ID: 9a1f3c5d7e2b
Revises: 2c7a2e1b4f6d
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "9a1f3c5d7e2b"
down_revision: Union[str, Sequence[str], None] = "2c7a2e1b4f6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "search_owner_state",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "last_applied_outbox_id",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_table("search_owner_state")
