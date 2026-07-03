from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

# Get the project root directory (where databases/ is located)
#PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # /home/chandru/binp51
#DATABASE_DIR = PROJECT_ROOT / "databases"
#DATABASE_DIR.mkdir(exist_ok=True)  # Ensure the databases folder exists
#
#URL_DATABASE = f"sqlite+aiosqlite:///{DATABASE_DIR / 'malmo_backend.db'}"


class Base(DeclarativeBase):
    pass


# This is the actual connection to the database - A fall back option if the postgres route does not work
async_url = settings.database_url_async
is_async_sqlite = async_url.startswith("sqlite")
if is_async_sqlite:
    engine = create_async_engine(async_url, echo=False,connect_args={"check_same_thread":False})
else:
    engine = create_async_engine(async_url,echo=False)


# Each request opens a session, uses the database and then closes it.
async_session_maker = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


# Create all the database and tables
async def create_db_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# Get a session to access the database to write and read from it
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


# Synchronous approach for celery tasks
# This is the actual connection to the database
sync_url = settings.database_url_sync
is_sqlite = sync_url.startswith("sqlite")
if is_sqlite:
    sync_engine = create_engine(sync_url, connect_args={"check_same_thread": False}) # connect args is only needed for SQLite database
else:
    sync_engine = create_engine(sync_url)

# Each request opens a session, uses the database and then closes it.
SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)
