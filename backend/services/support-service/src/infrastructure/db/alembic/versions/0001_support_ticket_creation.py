"""create support ticket creation schema

Revision ID: 0001_support_ticket_creation
Revises:
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_support_ticket_creation"
down_revision: Union[str, Sequence[str], None] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="OPEN"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("length(btrim(subject)) BETWEEN 1 AND 200", name="ck_tickets_subject_length"),
        sa.CheckConstraint("status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED')", name="ck_tickets_status"),
    )
    op.create_index("ix_tickets_author_created_at_id", "tickets", ["author_id", "created_at", "id"])
    op.create_table(
        "ticket_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.CheckConstraint("length(btrim(body)) BETWEEN 1 AND 10000", name="ck_ticket_messages_body_length"),
    )
    op.create_index("ix_ticket_messages_ticket_created_at_id", "ticket_messages", ["ticket_id", "created_at", "id"])
    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("aggregate_type", sa.Text(), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("trace_context", sa.Text()),
    )
    op.create_index("ix_outbox_messages_unpublished", "outbox_messages", ["id"], postgresql_where=sa.text("published_at IS NULL"))


def downgrade() -> None:
    op.drop_index("ix_outbox_messages_unpublished", table_name="outbox_messages")
    op.drop_table("outbox_messages")
    op.drop_index("ix_ticket_messages_ticket_created_at_id", table_name="ticket_messages")
    op.drop_table("ticket_messages")
    op.drop_index("ix_tickets_author_created_at_id", table_name="tickets")
    op.drop_table("tickets")
