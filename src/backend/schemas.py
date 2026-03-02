# This does only thing. It defines the shape of data your API accepts and returns
# What goes in and out of your API (Pydantic)

# User sends data -> Pydantic validates it -> SQLAlchemy savies it
# SQLAlchemy reads it -> Pydantic formats it -> User gets data OUT

from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, List

# This part is for user registration
class UserCreate(BaseModel):
    name: str
    email: str


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
    id: int
    sample_name: str
    username: str  # Changed from 'user' to 'username'
    email: str
    status: str
    submitted_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_msg: Optional[str] = None

    class Config:
        from_attributes = True # Allow reading from SQLAlchemy model


####### ABUNDANCE TABLE #######
"""

"""
class AbundanceItem(BaseModel):
    taxon_name: str
    taxon_id: Optional[str] = None
    taxon_rank: Optional[str] = None
    relative_abundance: float

    class Config:
        from_attributes = True

# Full results response for a sample
class SampleResults(BaseModel):
    sample_name: str
    status: str
    abundances: List[AbundanceItem]

