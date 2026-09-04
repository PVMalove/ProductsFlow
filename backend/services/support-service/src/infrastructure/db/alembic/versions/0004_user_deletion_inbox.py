"""support user deletion inbox and nullable identities

Revision ID: 0004_user_deletion_inbox
Revises: 0003_message_moderation
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_user_deletion_inbox"
down_revision: Union[str, Sequence[str], None] = "0003_message_moderation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "tickets",
        "author_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.alter_column(
        "ticket_messages",
        "author_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.create_table(
        "processed_messages",
        sa.Column("message_id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("processed_messages")
    op.alter_column(
        "ticket_messages",
        "author_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.alter_column(
        "tickets",
        "author_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
