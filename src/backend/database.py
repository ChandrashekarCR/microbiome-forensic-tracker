from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

URL_DATABASE = "sqlite:///databases/malmo_backend.db"
Path("databases").mkdir(exist_ok=True)

# This is the actual connection to the database
engine = create_engine(
    URL_DATABASE, connect_args={"check_same_thread": False}
)  # connect args is only needed for SQLite database

# Each request opens a session, uses the database and then closes it.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# This is like the parent class for all the tables
Base = declarative_base()


# This function is used in every API end point. It opens a database session, gives it to the endpoint and the closes it when done.
def get_db():
    db = SessionLocal()  # Opens the malmo_db database

    try:
        yield db  # Give it whichever API endpoint needs it
    finally:
        db.close()  # Then close the database at the end afeter utilizing it.
