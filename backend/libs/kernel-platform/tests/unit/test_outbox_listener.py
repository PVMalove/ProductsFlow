# ruff: noqa: E501
from kernel_platform.outbox.listener import to_asyncpg_dsn


def test_to_asyncpg_dsn_strips_the_sqlalchemy_driver_suffix() -> None:
    assert (
        to_asyncpg_dsn("postgresql+asyncpg://admin:admin@localhost:7610/identity")
        == "postgresql://admin:admin@localhost:7610/identity"
    )


def test_to_asyncpg_dsn_leaves_a_bare_postgresql_url_untouched() -> None:
    assert (
        to_asyncpg_dsn("postgresql://admin:admin@localhost:7610/identity")
        == "postgresql://admin:admin@localhost:7610/identity"
    )
