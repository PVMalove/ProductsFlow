"""payment authorizations

Revision ID: d74e30e2f89f
Revises:
Create Date: 2026-09-12 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d74e30e2f89f"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "payment_authorizations",
        # PK = свежий uuid.uuid4() (ADR 0006, issue #368) — не сам
        # idempotency-ключ (произвольная клиентская строка).
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("payment_method_token", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("void_idempotency_key", sa.Text(), nullable=True),
        sa.Column("capture_idempotency_key", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_payment_authorizations_idempotency_key"
        ),
        sa.UniqueConstraint(
            "void_idempotency_key", name="uq_payment_authorizations_void_idempotency_key"
        ),
        sa.UniqueConstraint(
            "capture_idempotency_key",
            name="uq_payment_authorizations_capture_idempotency_key",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("payment_authorizations")
