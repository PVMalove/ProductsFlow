"""order authorization and compensation: outbox command_type, payment
authorization id, per-source inbox key

Revision ID: 3230339cab9b
Revises: 301b0587179e
Create Date: 2026-10-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "3230339cab9b"
down_revision: Union[str, Sequence[str], None] = "301b0587179e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Postgres default name of the unnamed primary key created by 301b0587179e.
_PROCESSED_MESSAGES_PK = "processed_messages_pkey"


def upgrade() -> None:
    """Upgrade schema."""
    # Existing rows are all `inventory.reserve.v1` intents (issue #372).
    op.add_column(
        "reservation_outbox",
        sa.Column(
            "command_type",
            sa.Text(),
            nullable=False,
            server_default="inventory.reserve.v1",
        ),
    )
    op.alter_column("reservation_outbox", "command_type", server_default=None)

    op.add_column(
        "orders",
        sa.Column(
            "payment_authorization_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
    )

    # Every processed message so far came from inventory-service.
    op.add_column(
        "processed_messages",
        sa.Column("source", sa.Text(), nullable=False, server_default="inventory"),
    )
    op.drop_constraint(_PROCESSED_MESSAGES_PK, "processed_messages", type_="primary")
    op.create_primary_key(
        _PROCESSED_MESSAGES_PK, "processed_messages", ["source", "message_id"]
    )
    op.alter_column("processed_messages", "source", server_default=None)

    op.execute(
        "UPDATE orders SET saga_step = 'awaiting_authorization' "
        "WHERE saga_step = 'reservation_confirmed'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "UPDATE orders SET saga_step = 'reservation_confirmed' "
        "WHERE saga_step = 'awaiting_authorization'"
    )

    op.execute("DELETE FROM processed_messages WHERE source <> 'inventory'")
    op.drop_constraint(_PROCESSED_MESSAGES_PK, "processed_messages", type_="primary")
    op.create_primary_key(_PROCESSED_MESSAGES_PK, "processed_messages", ["message_id"])
    op.drop_column("processed_messages", "source")

    op.drop_column("orders", "payment_authorization_id")
    op.drop_column("reservation_outbox", "command_type")
