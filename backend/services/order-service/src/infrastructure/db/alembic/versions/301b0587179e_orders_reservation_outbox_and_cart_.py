"""orders, reservation_outbox, processed_messages and cart_lines lock columns

Revision ID: 301b0587179e
Revises: 58907723bd17
Create Date: 2026-09-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "301b0587179e"
down_revision: Union[str, Sequence[str], None] = "58907723bd17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "cart_lines",
        sa.Column("locked_by_order_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "cart_lines", sa.Column("unavailable_reason", sa.Text(), nullable=True)
    )

    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("saga_step", sa.Text(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_orders_user_id", "orders", ["user_id"], unique=False)

    op.create_table(
        "order_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_kopecks", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name="fk_order_lines_order_id_orders",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_order_lines_order_id", "order_lines", ["order_id"], unique=False)

    op.create_table(
        "idempotency_keys",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("request_fingerprint", sa.Text(), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "reservation_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempts", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_reservation_outbox_unpublished",
        "reservation_outbox",
        ["id"],
        postgresql_where=sa.text("published_at IS NULL"),
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
    """Downgrade schema."""
    op.drop_table("processed_messages")
    op.drop_index(
        "ix_reservation_outbox_unpublished", table_name="reservation_outbox"
    )
    op.drop_table("reservation_outbox")
    op.drop_table("idempotency_keys")
    op.drop_index("ix_order_lines_order_id", table_name="order_lines")
    op.drop_table("order_lines")
    op.drop_index("ix_orders_user_id", table_name="orders")
    op.drop_table("orders")
    op.drop_column("cart_lines", "unavailable_reason")
    op.drop_column("cart_lines", "locked_by_order_id")
