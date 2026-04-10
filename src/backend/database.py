from pathlib import Path
from collections.abc import AsyncGenerator

#from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import DeclarativeBase,sessionmaker

# Get the project root directory (where databases/ is located)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # /home/chandru/binp51
DATABASE_DIR = PROJECT_ROOT / "databases"
DATABASE_DIR.mkdir(exist_ok=True)  # Ensure the databases folder exists

URL_DATABASE = f"sqlite+aiosqlite:///{DATABASE_DIR / 'malmo_backend.db'}"

class Base(DeclarativeBase):
    pass

# This is the actual connection to the database
engine = create_async_engine(URL_DATABASE)
#engine = create_engine(URL_DATABASE, connect_args={"check_same_thread": False})  # connect args is only needed for SQLite database

# Each request opens a session, uses the database and then closes it.
#SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
async_session_maker = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

# This is like the parent class for all the tables
#Base = declarative_base()

# Create all the database and tables
async def create_db_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Get a session to access the database to write and read from it
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session

# This function is used in every API end point. It opens a database session, gives it to the endpoint and the closes it when done.
#def get_db():
#    db = SessionLocal()  # Opens the malmo_db database
#
#    try:
#        yield db  # Give it whichever API endpoint needs it
#    finally:
#        db.close()  # Then close the database at the end afeter utilizing it.
