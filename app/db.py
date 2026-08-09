from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DATABASE_URL = "sqlite+aiosqlite:///./market_store.db"


engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


event.listen(engine.sync_engine, "connect", _enable_sqlite_foreign_keys)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


Session = Annotated[AsyncSession, Depends(get_session)]


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: sync_conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    price REAL NOT NULL,
                    description TEXT NOT NULL DEFAULT ''
                )
                """)
            )
        )
