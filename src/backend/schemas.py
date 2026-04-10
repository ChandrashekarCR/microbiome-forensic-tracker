# This does only thing. It defines the shape of data your API accepts and returns
# What goes in and out of your API (Pydantic)

# User sends data -> Pydantic validates it -> SQLAlchemy saves it
# SQLAlchemy reads it -> Pydantic formats it -> User gets data in a correct formatted way

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel
import uuid


####### SAMPLE TABLE ########
"""
There are two pydantic schemas that will do the following -:
1) SamplCreate - To represent data expected when creating an item.
2) SampleResponse - To represent data to the user after a request has been made.
"""


# Create a sample when the user uploads
class SampleCreate(BaseModel):
    username: str
    email: str
    sample_name: str


# What is sent back after creating a sample
class SampleResponse(BaseModel):
    id: uuid.UUID
    sample_name: str
    username: str  # Changed from 'user' to 'username'
    email: str
    status: str
    submitted_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_msg: Optional[str] = None

    class Config:
        from_attributes = True  # Allow reading from SQLAlchemy model


####### ABUNDANCE TABLE #######
