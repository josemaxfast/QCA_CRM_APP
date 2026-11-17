from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings

url = context.config.get_main_option("sqlalchemy.url") or get_settings().migration_url
engine = create_engine(url)

with engine.connect() as conn:
    context.configure(connection=conn, transaction_per_migration=True)
    with context.begin_transaction():
        context.run_migrations()
