"""add product images and UUID-compatible audit actors

Revision ID: d45d8b8b8aba
Revises: 7e6095c037fb
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d45d8b8b8aba"
down_revision: Union[str, Sequence[str], None] = "7e6095c037fb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "product_audit_log",
        "actor_user_id",
        existing_type=sa.BigInteger(),
        type_=sa.Text(),
        postgresql_using="actor_user_id::text",
    )
    op.create_table(
        "product_images",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "product_id",
            sa.BigInteger(),
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


def downgrade() -> None:
    op.drop_table("product_images")
    op.alter_column(
        "product_audit_log",
        "actor_user_id",
        existing_type=sa.Text(),
        type_=sa.BigInteger(),
        # UUID actors cannot be represented by the legacy integer column;
        # preserve numeric legacy values and intentionally drop only UUIDs.
        postgresql_using=(
            "CASE WHEN actor_user_id ~ '^[0-9]+$' "
            "THEN actor_user_id::bigint ELSE NULL END"
        ),
    )
