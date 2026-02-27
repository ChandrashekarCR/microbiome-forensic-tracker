# This file contains all the function needed to talk the database

# Import Libraries
from sqlalchemy.orm import Session
from datetime import datetime
from backend.models import Samples, AbundanceResult
from backend.schemas import SampleCreate

def create_sample(db: Session, user:str, email:str, sample_name:str, r1_path: str,
                  r2_path:str,) -> Samples:
    """
    INSERT a new sample into the database
    Returns the created Sample object
    """

    new_sample = Samples(
        user = user,
        email = email,
        sample_name = sample_name,
        r1_path = r1_path,
        r2_path = r2_path,
        status = "pending"
    )

    db.add(new_sample) # Stage the insert
    db.commit() # Save it in the database
    db.refresh(new_sample) # Reload from database (gets auto-genrated id)
    return new_sample

def get_sample_by_name(db: Session, sample_name: str) -> Samples:
    """
    SELECT sample WHERE sample_name = ?
    Return Sample object or None
    """
    return db.query(Samples).filter(Samples.sample_name == sample_name).first()

def get_sample_by_id(db: Session, sample_id: int) -> Samples:
    """
    SELECT sample WHERE id = ?
    Return Sample object or None
    """
    return db.query(Samples).filter(Samples.id == sample_id).first()

def get_all_samples(db: Session) -> list[Samples]:
    """
    SELECT all samples, newest first
    """
    return db.query(Samples).order_by(Samples.submitted_at.desc()).all()

def update_sample_status(db: Session, sample_id: int, status: str):
    """
    UPDATE sample status and optional fields
    Eg.
        update_sample_status(db, 1, "processing", stated_at = datetime.now())
        update_sample_status(db, 1, "completed", completed_at = datetime.now())
        update_sample_status(db, 1, "failed", error_msg="Pipeline_crashed")
    """

    sample = db.query(Samples).filter(Samples.id == sample_id).first()

    if not sample:
        return None
    
    # Update any addittional files passed in
    db.commit()
    db.refresh(sample)
    return sample

