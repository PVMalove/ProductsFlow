"""support local user projection (ADR 0033)

Revision ID: 0005_user_projection
Revises: 0004_user_deletion_inbox
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_user_projection"
down_revision: Union[str, Sequence[str], None] = "0004_user_deletion_inbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_projection",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "last_applied_outbox_id",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_table("user_projection")
