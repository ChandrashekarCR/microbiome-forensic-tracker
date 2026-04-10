# Defines what the malmo_db database tables looks like
# Each class is a table in the database

# Importing libraries
import uuid
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.sql import func

from .database import Base


# Table 1: samples
# Tracks every sample uploaded by the users
class Samples(Base):
    __tablename__ = "samples"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sample_name = Column(String(200), index=True)  
    username = Column(String(100), index=True)
    email = Column(String(100))

    # File metadata
    r1_path = Column(String(500),nullable=False)  # the file path for forward read
    r2_path = Column(String(500), nullable=False)  # the file path for reverse read

    # Pipeiline status
    # pending -> processing -> completed/failed
    status = Column(String, default="pending")

    # Timestamps
    submitted_at = Column(DateTime(timezone=True), default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)




