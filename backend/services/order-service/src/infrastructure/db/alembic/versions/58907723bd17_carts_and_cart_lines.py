"""carts and cart_lines

Revision ID: 58907723bd17
Revises:
Create Date: 2026-09-12 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "58907723bd17"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "carts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", name="uq_carts_user_id"),
    )
    op.create_table(
        "cart_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cart_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["cart_id"], ["carts.id"], name="fk_cart_lines_cart_id_carts", ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "cart_id", "product_id", name="uq_cart_lines_cart_id_product_id"
        ),
        sa.CheckConstraint("quantity > 0", name="ck_cart_lines_quantity_positive"),
    )
    op.create_index(
        "ix_cart_lines_cart_id", "cart_lines", ["cart_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_cart_lines_cart_id", table_name="cart_lines")
    op.drop_table("cart_lines")
    op.drop_table("carts")
