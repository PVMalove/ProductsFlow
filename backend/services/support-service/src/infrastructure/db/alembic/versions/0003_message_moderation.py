"""add message moderation state

Revision ID: 0003_message_moderation
Revises: 0002_ticket_status_constraint
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_message_moderation"
down_revision: Union[str, Sequence[str], None] = "0002_ticket_status_constraint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ticket_messages",
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )


def downgrade() -> None:
    op.drop_column("ticket_messages", "is_deleted")
