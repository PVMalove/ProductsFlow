"""use UUIDs for product aggregate identifiers

Revision ID: f2b4a6c8d0e1
Revises: d45d8b8b8aba

The previous catalog schema used BIGINT product identifiers. There is no
lossless PostgreSQL cast from those values to UUID, and products are not yet
deployed with production data. Recreate the affected development tables so
the new schema is internally consistent.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f2b4a6c8d0e1"
down_revision: Union[str, Sequence[str], None] = "d45d8b8b8aba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Recreate product tables and change the empty outbox column to UUID."""
    _change_outbox_aggregate_id(
        existing_type=sa.BigInteger(), new_type=postgresql.UUID(as_uuid=True)
    )
    _drop_product_schema()
    _create_product_schema(
        product_id_type=postgresql.UUID(as_uuid=True), product_id_identity=False
    )


def downgrade() -> None:
    """Restore the previous BIGINT product schema."""
    _change_outbox_aggregate_id(
        existing_type=postgresql.UUID(as_uuid=True), new_type=sa.BigInteger()
    )
    _drop_product_schema()
    _create_product_schema(product_id_type=sa.BigInteger(), product_id_identity=True)


def _drop_product_schema() -> None:
    op.drop_table("product_images")
    op.drop_table("product_audit_log")
    op.drop_index("ix_products_is_active_created_at_id", table_name="products")
    op.drop_index("ix_products_user_id", table_name="products")
    op.drop_index("ix_products_price", table_name="products")
    op.drop_index("ix_products_category", table_name="products")
    op.drop_table("products")


def _change_outbox_aggregate_id(
    *, existing_type: sa.types.TypeEngine, new_type: sa.types.TypeEngine
) -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM outbox_messages) THEN
                RAISE EXCEPTION
                    'outbox_messages must be empty before changing aggregate_id type';
            END IF;
        END
        $$;
        """
    )
    op.alter_column(
        "outbox_messages",
        "aggregate_id",
        existing_type=existing_type,
        type_=new_type,
        existing_nullable=False,
        postgresql_using="aggregate_id::text::uuid"
        if isinstance(new_type, postgresql.UUID)
        else "aggregate_id::text::bigint",
    )


def _create_product_schema(
    *, product_id_type: sa.types.TypeEngine, product_id_identity: bool
) -> None:
    product_id = (
        sa.Column("id", product_id_type, sa.Identity(), primary_key=True)
        if product_id_identity
        else sa.Column("id", product_id_type, primary_key=True)
    )
    op.create_table(
        "products",
        product_id,
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
    _create_product_indexes()

    op.create_table(
        "product_audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("product_id", product_id_type, nullable=False),
        sa.Column("actor_user_id", sa.Text(), nullable=True),
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
        "product_images",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "product_id",
            product_id_type,
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("s3_key", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def _create_product_indexes() -> None:
    op.create_index("ix_products_category", "products", ["category"])
    op.create_index("ix_products_price", "products", ["price"])
    op.create_index("ix_products_user_id", "products", ["user_id"])
    op.create_index(
        "ix_products_is_active_created_at_id",
        "products",
        ["is_active", "created_at", "id"],
    )
