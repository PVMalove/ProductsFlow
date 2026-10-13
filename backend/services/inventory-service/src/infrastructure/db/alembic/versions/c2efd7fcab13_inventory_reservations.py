"""inventory reservations and command inbox

Revision ID: c2efd7fcab13
Revises: 1106f353bbf1
Create Date: 2026-09-12 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c2efd7fcab13"
down_revision: Union[str, Sequence[str], None] = "1106f353bbf1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "inventory",
        sa.Column(
            "reserved", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.create_check_constraint(
        "ck_inventory_reserved_le_quantity", "inventory", "reserved <= quantity"
    )

    op.create_table(
        "reservations",
        # PK = order_id (issue #370, D3) — один активный резерв на заказ,
        # закреплено уже на уровне схемы (тот же приём, что inventory.product_id).
        sa.Column("order_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_reservations_active_expires_at",
        "reservations",
        ["expires_at"],
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "reservation_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["reservations.order_id"],
            name="fk_reservation_lines_reservation_id_reservations",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "quantity > 0", name="ck_reservation_lines_quantity_positive"
        ),
    )
    op.create_index(
        "ix_reservation_lines_reservation_id",
        "reservation_lines",
        ["reservation_id"],
        unique=False,
    )

    # `inbox_messages` (issue #365's kernel-platform contract, ADR 0006) —
    # inventory-service becomes its first real `consume_command` consumer in
    # this ticket; the table was never added to this service's migration
    # history (issue #367 predates any command consumption here), so it's
    # added alongside the reservation schema it's needed for. Same shape as
    # catalog-service's b7c4d9e2a610_command_inbox.py.
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
    """Downgrade schema."""
    op.drop_table("inbox_messages")
    op.drop_index("ix_reservation_lines_reservation_id", table_name="reservation_lines")
    op.drop_table("reservation_lines")
    op.drop_index("ix_reservations_active_expires_at", table_name="reservations")
    op.drop_table("reservations")
    op.drop_constraint(
        "ck_inventory_reserved_le_quantity", "inventory", type_="check"
    )
    op.drop_column("inventory", "reserved")
