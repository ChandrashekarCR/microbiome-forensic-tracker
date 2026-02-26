from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, ForeignKey, Enum
from sqlalchemy.sql import func
from database import Base
from datetime import datetime
from enum import Enum as PyEnum
import uuid

class RunStatus(PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"

class Samples(Base):
    __tablename__ = 'samples'

    id = Column(Integer,primary_key=True,index=True)
    uuid = Column(String(36), unique=True, default=lambda: str(uuid.uuid4())) # Job ID 
    username = Column(String(100), index= True)
    email = Column(String(100))

    # File metadata
    sample_name = Column(String(200), index=True) # zr23059_100
    r1_path = Column(String(500)) # the file path for forward read
    r2_path = Column(String(500)) # the file path for reverse read

    # Pipeiline status
    status = Column(Enum(RunStatus),default=RunStatus.PENDING, index=True)
    submitted_at = Column(DateTime(timezone=True), default=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    
    # Result Tracking
    results_dir = Column(String(500)) # the file path to the results directory

    