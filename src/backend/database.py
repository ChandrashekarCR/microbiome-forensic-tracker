from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# Get the project root directory (where databases/ is located)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # /home/chandru/binp51
DATABASE_DIR = PROJECT_ROOT / "databases"
DATABASE_DIR.mkdir(exist_ok=True)  # Ensure the databases folder exists

URL_DATABASE = f"sqlite+aiosqlite:///{DATABASE_DIR / 'malmo_backend.db'}"


class Base(DeclarativeBase):
    pass


# This is the actual connection to the database
engine = create_async_engine(URL_DATABASE)


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
sync_url = f"sqlite:///{DATABASE_DIR / 'malmo_backend.db'}"

# This is the actual connection to the database
sync_engine = create_engine(sync_url, connect_args={"check_same_thread": False})  # connect args is only needed for SQLite database

# Each request opens a session, uses the database and then closes it.
SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)


