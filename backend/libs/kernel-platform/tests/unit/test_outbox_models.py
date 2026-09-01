from sqlalchemy.dialects.postgresql import UUID

from kernel_platform.outbox.models import OutboxMessage


def test_outbox_aggregate_id_uses_postgresql_uuid() -> None:
    aggregate_id = OutboxMessage.__table__.c.aggregate_id

    assert isinstance(aggregate_id.type, UUID)
    assert aggregate_id.type.as_uuid is True
