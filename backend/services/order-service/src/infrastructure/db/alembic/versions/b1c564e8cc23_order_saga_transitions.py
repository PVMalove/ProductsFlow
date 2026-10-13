"""order saga transitions: append-only Saga history journal

Revision ID: b1c564e8cc23
Revises: 3230339cab9b
Create Date: 2026-10-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b1c564e8cc23"
down_revision: Union[str, Sequence[str], None] = "3230339cab9b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # issue #376, D5: one row per (saga_step, status) change of an Order.
    # Existing Orders get no backfilled initial row (R7 of the brief).
    op.create_table(
        "order_saga_transitions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("saga_step", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name="fk_order_saga_transitions_order_id_orders",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_order_saga_transitions_order_id",
        "order_saga_transitions",
        ["order_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_order_saga_transitions_order_id", table_name="order_saga_transitions"
    )
    op.drop_table("order_saga_transitions")
