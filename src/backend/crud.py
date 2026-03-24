# This file contains all the function needed to talk the database
# This is used to create, read, update and delete things in the database CRUD operations

# Import Libraries
from sqlalchemy.orm import Session
from .models import Samples, AbundanceResult, User
from .schemas import SampleCreate, UserCreate

# Create a new sample when the user uploads the fastq samples
def create_sample(db: Session, username:str, email:str, sample_name:str, r1_path: str,
                  r2_path:str,) -> Samples:
    """
    INSERT a new sample into the database
    Returns the created Sample object
    """

    new_sample = Samples(
        username = username,
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

# This is just and end point for the user to see the status of the sample based on the name
def get_sample_by_name(db: Session, sample_name: str) -> Samples:
    """
    SELECT sample WHERE sample_name = ?
    Return Sample object or None
    """
    return db.query(Samples).filter(Samples.sample_name == sample_name).first()

# This is another end point to get the sample based on the sample id
def get_sample_by_id(db: Session, sample_id: int) -> Samples:
    """
    SELECT sample WHERE id = ?
    Return Sample object or None
    """
    return db.query(Samples).filter(Samples.id == sample_id).first()

# Get all the sample in the database
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

def create_abundance_results(db: Session, sample_id: int, results: list[dict]):
    """
    INSERT abundance results for a sample

    results = [
        {
            "taxon_name" : "E.coli", "taxon_id":462,
            "relative_abundance": 0.4
        }
    ]
    """

    db_results = []
    for row in results:
        result = AbundanceResult(
            sample_id = sample_id,
            taxon_name = row.get("taxon_name"),
            taxon_id = row.get("taxon_id"),
            taxon_rank = row.get("taxon_rank"),
            relative_abundance = row.get("relative_abundance")
        )
        db_results.append(result)

    db.add_all(db_results)
    db.commit()


def get_results_for_sample(db: Session, sample_id: int) -> list[AbundanceResult]:
    """
    SELECT all abundance results for a sample
    Ordered by relative_abundance descending
    """
    return (
        db.query(AbundanceResult)
        .filter(AbundanceResult.sample_id == sample_id)
        .order_by(AbundanceResult.relative_abundance.desc())
        .all()
    )

def create_user(db: Session, user: UserCreate):
    db_user = User(name=user.username, email = user.email)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)