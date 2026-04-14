# Defines what the malmo_db database tables looks like
# Each class is a table in the database

# Importing libraries
import uuid

from sqlalchemy import Column, DateTime, String, Integer, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from .database import Base


# Table 1: samples
# Tracks every sample uploaded by the users
class Samples(Base):
    __tablename__ = "samples"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sample_name = Column(String(200), index=True)
    username = Column(String(100), index=True)
    email = Column(String(100))

    # File metadata
    r1_path = Column(String(500), nullable=False)  # the file path for forward read
    r2_path = Column(String(500), nullable=False)  # the file path for reverse read

    # Pipeiline status
    # pending -> processing -> completed/failed
    status = Column(String, default="pending")

    # Timestamps
    submitted_at = Column(DateTime(timezone=True), default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Celery task tracking
    celery_task_id = Column(String(200), nullable=True)  # UUID of the Celery task
    error_msg = Column(String, nullable=True)  # Error message if pipeline fails
    log_path = Column(String, nullable=True)  # Path to Snakemake log file

# Table 2: abundance
# This table consists of the rsa values of the processed samples
class Abundance(Base):
    __tablename__ = "abundance"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sample_id = Column(String(36),ForeignKey('samples.id'),nullable=False, index=True)
    sample_name = Column(String(200), index=True)
    classifier = Column(String(200),nullable=False)
    clade = Column(String(400),nullable=False)
    taxa_id = Column(Integer, nullable=False)
    rank = Column(String(200),nullable=False)
    relative_abundance = Column(Float, nullable=False)