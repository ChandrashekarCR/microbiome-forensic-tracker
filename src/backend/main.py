from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Depends
from sqlalchemy.orm import Session
from pathlib import Path
from .database import engine, get_db
from .models import Base
from . import crud
from .schemas import UserCreate, SampleCreate, SampleResponse
from fastapi.responses import JSONResponse
import shutil

# Create all tables in the database on startup
Base.metadata.create_all(bind=engine)

# FastAPI app
app = FastAPI(
    title="Microdentify API",
    description="Metagenomic sample processing, location prediction and profile estimation",
    version="1.0.0"
)

# Create a directory to store the uploaded files
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@app.get("/", include_in_schema=False)
async def root():
    return {"message":"Microdentify",
            "status":"running"            
            }

# Upload a new sample
@app.post("/samples", response_model=SampleResponse, status_code=201)
async def upload_sample(
    background_task: BackgroundTasks,
    username: str,
    email: str,
    sample_name: str,
    r1: UploadFile = File(..., description="Forward read R1.fastq.gz"),
    r2: UploadFile = File(..., description="Forward read R2.fastq.gz"),
    db: Session = Depends(get_db) #Injects database session
):
    """
    Upload paired FASTQ files and trigger Snakemake pipeline
    
    Depends(get_db):
    - FastAPI calls get_db() automatically
    - Gives you a database session
    - Closes it when request is done
    """
    
    # Check if sample already exists
    if crud.get_sample_by_name(db, sample_name):
        raise HTTPException(
            status_code=400,
            detail=f"Sample '{sample_name}' already exists"
        )
    
    # Validate file extensions
    for f, name in [(r1, "R1"), (r2, "R2")]:
        if not f.filename.endswith(('.fastq.gz', '.fq.gz')):
            raise HTTPException(
                status_code=400,
                detail=f"{name} must be .fastq.gz or .fq.gz"
            )
    
    # Save uploaded files to disk
    sample_dir = UPLOAD_DIR / sample_name
    sample_dir.mkdir(parents=True, exist_ok=True)
    
    r1_path = sample_dir / f"{sample_name}_R1.fastq.gz"
    r2_path = sample_dir / f"{sample_name}_R2.fastq.gz"
    
    with open(r1_path, "wb") as f:
        shutil.copyfileobj(r1.file, f)
    with open(r2_path, "wb") as f:
        shutil.copyfileobj(r2.file, f)
    
    # 4. Create database record
    sample = crud.create_sample(
        db=db,
        username=username,  # Changed from 'user' to 'username'
        email=email,
        sample_name=sample_name,
        r1_path=str(r1_path),
        r2_path=str(r2_path)
    )
    
    # 5. Queue pipeline in background (doesn't block the response)
    
    # 6. Return immediately with "pending" status
    return sample


@app.get("/samples")
def list_samples(db: Session = Depends(get_db)):
    """List all submitted samples"""
    samples = crud.get_all_samples(db)
    return {
        "total": len(samples),
        "samples": [
            {
                "id": s.id,
                "sample_name": s.sample_name,
                "user": s.user,
                "status": s.status,
                "submitted_at": s.submitted_at
            }
            for s in samples
        ]
    }
