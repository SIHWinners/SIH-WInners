import asyncio
from logging.config import fileConfig

from sqlalchemy.engine import Connection

from alembic import context
from app.config import get_settings
from app.db import models  # noqa: F401  (register tables)
from app.db.base import Base
from app.db.session import get_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)
target_metadata = Base.metadata


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=get_settings().is_sqlite,  # SQLite needs batch mode for ALTERs
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async() -> None:
    engine = get_engine()
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_async())
