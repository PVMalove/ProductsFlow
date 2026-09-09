"""add command inbox

Revision ID: b7c4d9e2a610
Revises: 9a1f3c5d7e2b
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b7c4d9e2a610"
down_revision: Union[str, Sequence[str], None] = "9a1f3c5d7e2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "inbox_messages",
        sa.Column("command_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("command_type", sa.Text(), nullable=False),
        sa.Column("causation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_id", sa.Text(), nullable=False),
        sa.Column("trace_context", sa.Text(), nullable=True),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("inbox_messages")
