"""outbox messages notify trigger

Revision ID: 05fc06c154bc
Revises: 672e9d689f15
Create Date: 2026-08-29 17:13:29.705733

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '05fc06c154bc'
down_revision: Union[str, Sequence[str], None] = '672e9d689f15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Канал должен совпадать буквально с kernel_platform.outbox.listener.NOTIFICATION_CHANNEL
# — оба конца (INSERT-триггер здесь, LISTEN в OutboxListener) координируются
# только через это имя, без общего импорта между Alembic и приложением.
NOTIFICATION_CHANNEL = "outbox_messages_inserted"


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        f"""
        CREATE FUNCTION notify_outbox_insert() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify('{NOTIFICATION_CHANNEL}', NEW.id::text);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER outbox_messages_notify_insert
        AFTER INSERT ON outbox_messages
        FOR EACH ROW EXECUTE FUNCTION notify_outbox_insert();
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER outbox_messages_notify_insert ON outbox_messages;")
    op.execute("DROP FUNCTION notify_outbox_insert();")
