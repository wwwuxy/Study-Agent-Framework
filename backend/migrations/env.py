from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.settings import Settings
from app.db.models import Base
import app.exam_diagnostics.models  # noqa: F401

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name, disable_existing_loggers=False)
config.set_main_option("sqlalchemy.url", Settings().database_url.replace("%", "%%"))
target_metadata = Base.metadata


if context.is_offline_mode():
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = engine_from_config(
        config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
