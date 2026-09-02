"""constrain support ticket lifecycle statuses

Revision ID: 0002_ticket_status_constraint
Revises: 0001_support_ticket_creation
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002_ticket_status_constraint"
down_revision: Union[str, Sequence[str], None] = "0001_support_ticket_creation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_tickets_status",
        "tickets",
        "status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_tickets_status", "tickets", type_="check")
