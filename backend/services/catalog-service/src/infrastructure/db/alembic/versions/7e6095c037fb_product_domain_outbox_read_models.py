"""product domain, outbox, owner read model, processed messages

Revision ID: 7e6095c037fb
Revises:
Create Date: 2026-08-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "7e6095c037fb"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column(
            "description", sa.Text(), nullable=False, server_default=sa.text("''")
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_products_category", "products", ["category"])
    op.create_index("ix_products_price", "products", ["price"])
    op.create_index("ix_products_user_id", "products", ["user_id"])
    op.create_index(
        "ix_products_is_active_created_at_id",
        "products",
        ["is_active", "created_at", "id"],
    )

    op.create_table(
        "product_audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        # Без ForeignKey — audit-строка переживает удаление Товара
        # (CONTEXT.md «Существование продукта», как и в монолите, ADR 0008).
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column(
            "description", sa.Text(), nullable=False, server_default=sa.text("''")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("aggregate_type", sa.Text(), nullable=False),
        sa.Column("aggregate_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempts", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_context", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_outbox_messages_unpublished",
        "outbox_messages",
        ["id"],
        postgresql_where=sa.text("published_at IS NULL"),
    )

    op.create_table(
        "owner_read_model",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "last_applied_outbox_id",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
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
    op.drop_table("owner_read_model")
    op.drop_index("ix_outbox_messages_unpublished", table_name="outbox_messages")
    op.drop_table("outbox_messages")
    op.drop_table("product_audit_log")
    op.drop_index("ix_products_is_active_created_at_id", table_name="products")
    op.drop_index("ix_products_user_id", table_name="products")
    op.drop_index("ix_products_price", table_name="products")
    op.drop_index("ix_products_category", table_name="products")
    op.drop_table("products")
