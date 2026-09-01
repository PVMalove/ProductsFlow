"""change outbox aggregate_id to uuid

Revision ID: c1a7e6e6a4f2
Revises: 05fc06c154bc
Create Date: 2026-09-01 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c1a7e6e6a4f2"
down_revision: Union[str, Sequence[str], None] = "05fc06c154bc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM outbox_messages) THEN
                RAISE EXCEPTION
                    'outbox_messages must be empty before changing aggregate_id to UUID; drain or delete legacy messages first';
            END IF;
        END
        $$;
        """
    )
    op.alter_column(
        "outbox_messages",
        "aggregate_id",
        existing_type=sa.BigInteger(),
        type_=postgresql.UUID(as_uuid=True),
        existing_nullable=False,
        # The legacy column is expected to be empty before this breaking
        # migration; numeric values are not valid aggregate UUIDs.
        postgresql_using="aggregate_id::text::uuid",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM outbox_messages) THEN
                RAISE EXCEPTION
                    'outbox_messages must be empty before downgrading aggregate_id from UUID to BIGINT';
            END IF;
        END
        $$;
        """
    )
    op.alter_column(
        "outbox_messages",
        "aggregate_id",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.BigInteger(),
        existing_nullable=False,
        postgresql_using="aggregate_id::text::bigint",
    )
