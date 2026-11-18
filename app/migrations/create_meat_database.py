import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from core.config import settings


async def create_meat_database() -> None:
    database = settings.postgres_meat_db
    engine = create_async_engine(
        url=settings.database_url.set(
            database="postgres",
        ),
        isolation_level="AUTOCOMMIT",
    )
    try:
        async with engine.connect() as connection:
            # the server releases this lock when the connection closes
            await connection.execute(
                statement=text(
                    "SELECT pg_advisory_lock(hashtext('schetovod:create_meat_database'))",
                ),
            )
            is_template = await connection.scalar(
                statement=text(
                    "SELECT datistemplate FROM pg_database WHERE datname = :database",
                ),
                parameters={"database": database},
            )
            if is_template:
                raise ValueError(
                    "POSTGRES_MEAT_DB не может указывать на шаблон базы PostgreSQL",
                )
            if is_template is None:
                quoted_database = engine.dialect.identifier_preparer.quote_identifier(
                    value=database,
                )
                await connection.exec_driver_sql(
                    statement=f"CREATE DATABASE {quoted_database}",
                )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(
        main=create_meat_database(),
    )
